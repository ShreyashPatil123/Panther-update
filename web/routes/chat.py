"""Chat, session, and file-upload routes."""
import os
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

router = APIRouter()

UPLOAD_DIR = Path("./data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── REST: session list ──────────────────────────────────────────────────────

@router.get("/api/sessions")
async def get_sessions(request: Request):
    """Return all chat sessions ordered by most-recently updated."""
    orchestrator = request.app.state.orchestrator
    try:
        sessions = await orchestrator.memory.get_sessions()
        return JSONResponse(sessions)
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return JSONResponse([], status_code=200)


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete a session and all its messages."""
    orchestrator = request.app.state.orchestrator
    try:
        await orchestrator.memory.delete_session(session_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request):
    """Return all messages for a specific session."""
    orchestrator = request.app.state.orchestrator
    try:
        messages = await orchestrator.memory.get_recent_messages(
            limit=200, session_id=session_id
        )
        return JSONResponse(messages)
    except Exception as e:
        logger.error(f"Failed to get messages for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── REST: file upload ───────────────────────────────────────────────────────

@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Save an uploaded file and return its server-side path."""
    try:
        safe_name = f"{uuid.uuid4().hex}_{file.filename}"
        dest = UPLOAD_DIR / safe_name
        content = await file.read()
        dest.write_bytes(content)
        logger.info(f"Uploaded file saved: {dest}")
        return JSONResponse({"path": str(dest), "name": file.filename})
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket: streaming chat ───────────────────────────────────────────────

@router.websocket("/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming chat.

    Protocol (client → server):
        { "text": "...", "attachments": ["/path/to/file", ...] }
        { "action": "switch_session", "session_id": "..." }
        { "action": "new_session" }
        { "action": "set_category", "category": "code" }

    Protocol (server → client):
        { "type": "chunk",   "text": "..." }          — streaming token
        { "type": "done"  }                            — end of response
        { "type": "error",   "text": "..." }           — error message
        { "type": "session", "session_id": "...",      — active session info
                             "sessions": [...] }
    """
    orchestrator = websocket.app.state.orchestrator
    await websocket.accept()

    # Attach to session
    orchestrator.current_session_id = session_id

    # Send current session info
    try:
        sessions = await orchestrator.memory.get_sessions()
    except Exception:
        sessions = []

    await websocket.send_json({
        "type": "session",
        "session_id": session_id,
        "sessions": sessions,
    })

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "switch_session":
                new_sid = data.get("session_id", session_id)
                orchestrator.current_session_id = new_sid
                session_id = new_sid
                messages = await orchestrator.memory.get_recent_messages(
                    limit=200, session_id=session_id
                )
                sessions = await orchestrator.memory.get_sessions()
                await websocket.send_json({
                    "type": "session",
                    "session_id": session_id,
                    "sessions": sessions,
                    "history": messages,
                })
                continue

            if action == "new_session":
                session_id = str(uuid.uuid4())
                orchestrator.current_session_id = session_id
                sessions = await orchestrator.memory.get_sessions()
                await websocket.send_json({
                    "type": "session",
                    "session_id": session_id,
                    "sessions": sessions,
                    "history": [],
                })
                continue

            if action == "set_category":
                from src.core.model_router import TaskCategory, get_task_preset
                cat_val = data.get("category", "")
                try:
                    category = TaskCategory(cat_val) if cat_val else None
                    orchestrator.set_task_category(category)
                    # Tell frontend which model is now active
                    if category:
                        preset = get_task_preset(category)
                        await websocket.send_json({
                            "type": "model_set",
                            "model": preset.model,
                            "provider": orchestrator.active_provider,
                        })
                except ValueError:
                    pass
                continue

            if action == "set_model":
                model_id = data.get("model_id", "").strip()
                provider  = data.get("provider", "nvidia")
                if model_id:
                    config = websocket.app.state.config
                    if provider == "ollama":
                        config.default_model = model_id
                        config.ollama_enabled = True
                        config.ollama_model   = model_id
                        api_key  = getattr(config, "ollama_api_key", None) or "ollama"
                        base_url = (config.ollama_base_url or "http://localhost:11434/v1").rstrip("/")
                        orchestrator.set_api_key(api_key, base_url=base_url, provider="ollama")
                    elif provider == "gemini":
                        google_key = getattr(config, "google_api_key", None) or ""
                        if not google_key:
                            await websocket.send_json({
                                "type": "error",
                                "text": "Google API key not configured. Add it in Settings first.",
                            })
                            continue
                        config.default_model = model_id
                        config.ollama_enabled = False
                        orchestrator.set_api_key(
                            google_key,
                            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                            provider="gemini",
                        )
                    else:  # nvidia
                        nvidia_key = orchestrator._original_nvidia_key or config.nvidia_api_key or ""
                        if not nvidia_key or nvidia_key == "your_api_key_here":
                            await websocket.send_json({
                                "type": "error",
                                "text": "NVIDIA API key not configured. Add it in Settings first.",
                            })
                            continue
                        config.default_model = model_id
                        config.ollama_enabled = False
                        orchestrator.set_api_key(nvidia_key, provider="nvidia")
                    logger.info(f"Model switched via WS: {model_id} ({provider})")
                    await websocket.send_json({"type": "model_set", "model": model_id, "provider": provider})
                continue

            if action == "delete_session":
                del_sid = data.get("session_id", "")
                if del_sid:
                    await orchestrator.memory.delete_session(del_sid)
                    if del_sid == session_id:
                        session_id = str(uuid.uuid4())
                        orchestrator.current_session_id = session_id
                sessions = await orchestrator.memory.get_sessions()
                await websocket.send_json({
                    "type": "session",
                    "session_id": session_id,
                    "sessions": sessions,
                    "history": [],
                })
                continue

            if action == "bulk_delete_sessions":
                del_sids = data.get("session_ids", [])
                cleared_current = False
                for sid in del_sids:
                    await orchestrator.memory.delete_session(sid)
                    if sid == session_id:
                        cleared_current = True
                
                if cleared_current:
                    session_id = str(uuid.uuid4())
                    orchestrator.current_session_id = session_id

                sessions = await orchestrator.memory.get_sessions()
                
                resp = {
                    "type": "session",
                    "session_id": session_id,
                    "sessions": sessions,
                }
                
                if cleared_current:
                    resp["history"] = []
                
                await websocket.send_json(resp)
                continue

            # ── Normal chat message ──
            text = data.get("text", "").strip()
            attachments: List[str] = data.get("attachments", [])

            if not text:
                continue

            try:
                if attachments:
                    gen = orchestrator.process_message_with_attachments(text, attachments)
                else:
                    gen = orchestrator.process_message(text)

                async for chunk in gen:
                    await websocket.send_json({"type": "chunk", "text": chunk})

                # Refresh session list (title may have been auto-assigned)
                sessions = await orchestrator.memory.get_sessions()
                await websocket.send_json({
                    "type": "done",
                    "sessions": sessions,
                    "session_id": orchestrator.current_session_id,
                })

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await websocket.send_json({"type": "error", "text": str(e)})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass
