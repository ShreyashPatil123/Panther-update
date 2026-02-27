"""Voice Command API — Routes voice transcripts through AgentOrchestrator via SSE."""

import asyncio
import json
import uuid
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["voice"])


# ── Request / Response Models ─────────────────────────────────────────────────

class VoiceCommandRequest(BaseModel):
    text: str                          # Transcript from Gemini Live
    session_id: Optional[str] = None   # Reuse existing session if provided
    confirmed: bool = False            # True if user confirmed a destructive action


# ── Session helpers ───────────────────────────────────────────────────────────

async def _create_voice_session(orchestrator) -> str:
    """Create a new named voice session in MemorySystem."""
    session_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%b %d, %I:%M %p")
    title = f"🎤 Voice — {timestamp}"
    await orchestrator.memory.create_session(session_id, title=title)
    return session_id


# ── Route: voice command ──────────────────────────────────────────────────────

@router.post("/voice-command")
async def voice_command(request: Request, body: VoiceCommandRequest) -> StreamingResponse:
    """
    Accept a voice transcript, route through AgentOrchestrator, stream SSE.

    SSE event types:
      - session    : session_id assigned to this voice conversation
      - progress   : status update while agent is working
      - result     : final full-text response
      - summary    : short TTS-friendly spoken summary
      - confirmation_required : destructive action needs user approval
      - error      : something went wrong
      - done       : stream complete
    """
    if not body.text or len(body.text.strip()) < 2:
        raise HTTPException(status_code=400, detail="Empty voice command")

    orchestrator = request.app.state.orchestrator

    return StreamingResponse(
        _stream_voice_response(body, orchestrator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/voice-session/{session_id}/close")
async def close_voice_session(session_id: str):
    """Called when the voice overlay closes. Non-critical."""
    return {"status": "closed", "session_id": session_id}


# ── SSE Generator ─────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_voice_response(
    req: VoiceCommandRequest,
    orchestrator,
) -> AsyncGenerator[str, None]:

    try:
        # ── 1. Resolve or create session ──────────────────────────────────
        session_id = req.session_id
        if not session_id:
            session_id = await _create_voice_session(orchestrator)
            yield _sse("session", {"session_id": session_id})

        yield _sse("progress", {
            "step": "routing",
            "message": "Understanding your request...",
        })

        # ── 2. Classify intent (for confirmation gate) ────────────────────
        intent = await orchestrator._classify_intent(req.text)
        logger.info(f"Voice intent: {intent} — '{req.text[:60]}'")

        # If it's just a chat, ignore it and let Gemini Live's own voice handle it
        if intent == "chat":
            yield _sse("ignored", {"reason": "chat"})
            return

        # ── 3. Confirmation gate for destructive actions ──────────────────
        if _is_destructive(intent, req.text) and not req.confirmed:
            prompt = _build_confirmation_prompt(intent, req.text)
            yield _sse("confirmation_required", {
                "intent": intent,
                "prompt": prompt,
                "original_text": req.text,
                "session_id": session_id,
            })
            return

        # ── 4. Progress events ────────────────────────────────────────────
        async for msg in _intent_progress_events(intent):
            yield _sse("progress", msg)

        # ── 5. Run through AgentOrchestrator ──────────────────────────────
        # Set session context
        orchestrator.current_session_id = session_id

        # Collect streamed chunks into full result
        result_chunks = []
        try:
            async for chunk in orchestrator.process_message(req.text):
                result_chunks.append(chunk)
                # Stream chunks incrementally to frontend
                yield _sse("chunk", {"text": chunk})
        except asyncio.TimeoutError:
            yield _sse("error", {
                "code": "TIMEOUT",
                "message": "The agent took too long. Try a simpler request.",
            })
            return

        full_result = "".join(result_chunks)

        # ── 6. Generate spoken summary ────────────────────────────────────
        spoken_summary = await _generate_spoken_summary(
            full_result, intent, orchestrator, original_text=req.text
        )

        # ── 7. Emit result + summary + done ───────────────────────────────
        yield _sse("result", {
            "session_id": session_id,
            "intent": intent,
            "text": full_result,
        })
        yield _sse("summary", {"text": spoken_summary})
        yield _sse("done", {"session_id": session_id})

    except Exception as e:
        logger.exception(f"Voice command failed: {req.text[:80]}")
        yield _sse("error", {
            "code": "AGENT_ERROR",
            "message": f"Something went wrong: {str(e)[:200]}",
        })


# ── Helpers ───────────────────────────────────────────────────────────────────

DESTRUCTIVE_INTENTS = set()  # Browser tasks no longer need confirmation


def _is_destructive(intent: str, text: str) -> bool:
    """Determine if this action needs user confirmation."""
    if intent in DESTRUCTIVE_INTENTS:
        return True
    if intent == "file_operation":
        write_kw = ["write", "save", "create", "delete", "remove", "edit", "modify", "overwrite"]
        return any(kw in text.lower() for kw in write_kw)
    return False


def _build_confirmation_prompt(intent: str, text: str) -> str:
    """Build a natural-language confirmation prompt for TTS."""
    if intent == "browser_task":
        return f'I\'m about to control your browser for: "{text}". Say yes to proceed or cancel to stop.'
    if intent == "file_operation":
        return f'This will modify your file system for: "{text}". Say yes to proceed or cancel to stop.'
    return f'Please confirm: "{text}". Say yes or cancel.'


async def _intent_progress_events(intent: str):
    """Yield human-readable progress messages per intent."""
    messages = {
        "finance": [
            {"step": "resolve",   "message": "📈 Identifying ticker symbol..."},
            {"step": "fetch",     "message": "💹 Fetching live market data..."},
        ],
        "research": [
            {"step": "search",     "message": "🔍 Searching the web..."},
            {"step": "scrape",     "message": "📄 Reading relevant pages..."},
            {"step": "synthesize", "message": "🧠 Synthesizing findings..."},
        ],
        "browser_task": [
            {"step": "browser",    "message": "🌐 Opening browser..."},
            {"step": "navigate",   "message": "🖱️ Navigating to page..."},
        ],
        "file_operation": [
            {"step": "file",       "message": "📁 Accessing file system..."},
        ],
        "chat": [
            {"step": "thinking",   "message": "💭 Thinking..."},
        ],
    }
    for msg in messages.get(intent, [{"step": "working", "message": "Working on it..."}]):
        yield msg
        await asyncio.sleep(0.05)


async def _generate_spoken_summary(
    full_response: str,
    intent: str,
    orchestrator,
    original_text: str = ""
) -> str:
    """
    Summarize the full response into 2-3 TTS-friendly sentences.
    For browser tasks, generate a very short distinct success/failure message
    in the SAME LANGUAGE as the user's original prompt.
    """
    # Specifically intercept browser tasks for a much better voice UX
    if intent == "browser_task":
        is_success = "error" not in full_response.lower() and "failed" not in full_response.lower()
        
        if is_success:
            summary_prompt = (
                f"The user said: '{original_text}'. I just successfully opened the requested website. "
                f"REPLY ONLY WITH a short, natural confirmation in the EXACT SAME LANGUAGE the user used. "
                f"Example English: 'Opening YouTube.' Example Hindi: 'YouTube ओपन कर रहा हूँ।' "
                f"DO NOT add any conversational filler, just the confirmation."
            )
        else:
            summary_prompt = (
                f"The user said: '{original_text}'. I failed to open the website. "
                f"REPLY ONLY WITH a short apology in the EXACT SAME LANGUAGE the user used. "
                f"Example English: 'I couldn't open that website.' Example Hindi: 'मैं वह वेबसाइट ओपन नहीं कर पाया।' "
            )
    else:
        # Standard summary for research/finance/chat
        if len(full_response) <= 500:
            return full_response

        summary_prompt = (
            f"You are a strict summarizer for a voice assistant. Your job is to extract the EXACT FACTUAL ANSWER "
            f"from the text below and state it directly in 1-2 sentences. \n\n"
            f"CRITICAL RULES:\n"
            f"1. NEVER give meta-commentary (do NOT say 'I am locating', 'Based on the text', 'Here is the summary', etc.)\n"
            f"2. State the actual numbers, facts, or data directly.\n"
            f"3. Do not use bullet points, markdown, or special characters. Speak naturally.\n\n"
            f"TEXT TO SUMMARIZE:\n"
            f"{full_response[:3000]}"
        )

    try:
        messages = [{"role": "user", "content": summary_prompt}]
        chunks = []
        async for chunk in orchestrator.nvidia_client.chat_completion(
            messages,
            model=orchestrator.config.default_model,
            max_tokens=64,
            temperature=0.0
        ):
            chunks.append(chunk)

        result = "".join(chunks).strip()
        # Clean up any residual markdown that might sneak in
        result = result.replace("**", "").replace("*", "").replace("_", "")
        return result

    except Exception:
        # Fallback: first 300 chars
        return full_response[:300] + "..."
