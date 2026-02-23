"""Compare mode — run the same prompt across multiple models in parallel."""
import asyncio
import time
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from src.api.nvidia_client import NVIDIAClient

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_provider_credentials(config, provider: str) -> Tuple[str, str]:
    """Return (api_key, base_url) for a given provider using app config."""
    if provider == "nvidia":
        key = config.nvidia_api_key or ""
        url = "https://integrate.api.nvidia.com/v1"
    elif provider == "ollama":
        key = getattr(config, "ollama_api_key", None) or "ollama"
        url = (config.ollama_base_url or "http://localhost:11434/v1").rstrip("/")
    elif provider == "gemini":
        key = getattr(config, "google_api_key", None) or ""
        url = "https://generativelanguage.googleapis.com/v1beta/openai"
    else:
        raise ValueError(f"Unknown provider: {provider}")
    return key, url


async def _stream_slot(
    ws: WebSocket,
    config,
    slot_conf: Dict[str, Any],
    prompt: str,
) -> None:
    """Stream a single comparison slot — ephemeral client, tagged chunks."""
    slot_id = slot_conf["slot_id"]
    model_id = slot_conf["model_id"]
    provider = slot_conf.get("provider", "nvidia")
    temperature = slot_conf.get("temperature", 0.7)
    max_tokens = slot_conf.get("max_tokens", 4096)
    top_p = slot_conf.get("top_p", 1.0)

    # Resolve credentials
    try:
        api_key, base_url = _resolve_provider_credentials(config, provider)
    except ValueError as e:
        await ws.send_json({"type": "compare_error", "slot_id": slot_id, "text": str(e)})
        return

    if not api_key or (provider == "nvidia" and api_key == "your_api_key_here"):
        await ws.send_json({
            "type": "compare_error",
            "slot_id": slot_id,
            "text": f"{provider.title()} API key not configured.",
        })
        return

    client = NVIDIAClient(api_key=api_key, base_url=base_url, timeout=120.0)
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": "You are a helpful AI assistant. Use markdown formatting."},
        {"role": "user", "content": prompt},
    ]

    start = time.monotonic()
    ttft: float = 0
    first_chunk = True
    token_estimate = 0

    try:
        async for chunk in client.chat_completion(
            messages,
            model=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=True,
        ):
            if first_chunk:
                ttft = (time.monotonic() - start) * 1000
                first_chunk = False
            token_estimate += max(1, len(chunk.split()))
            await ws.send_json({
                "type": "compare_chunk",
                "slot_id": slot_id,
                "text": chunk,
            })

        total_ms = (time.monotonic() - start) * 1000
        await ws.send_json({
            "type": "compare_done",
            "slot_id": slot_id,
            "meta": {
                "model": model_id,
                "provider": provider,
                "ttft_ms": round(ttft, 1),
                "total_ms": round(total_ms, 1),
                "token_count": token_estimate,
            },
        })

    except asyncio.CancelledError:
        # Slot was cancelled — no message needed
        pass
    except Exception as e:
        logger.error(f"Compare slot {slot_id} ({model_id}) error: {e}")
        try:
            await ws.send_json({
                "type": "compare_error",
                "slot_id": slot_id,
                "text": str(e),
            })
        except Exception:
            pass
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def _await_all_and_signal(
    ws: WebSocket,
    tasks: Dict[int, asyncio.Task],
) -> None:
    """Wait for every slot task to finish, then send the all-done signal."""
    await asyncio.gather(*tasks.values(), return_exceptions=True)
    try:
        await ws.send_json({"type": "compare_all_done"})
    except Exception:
        pass


# ── WebSocket endpoint ────────────────────────────────────────────────────────


@router.websocket("/ws/compare/{session_id}")
async def ws_compare(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for compare mode.

    Protocol (client → server):
        { "action": "compare", "prompt": "...", "slots": [...] }
        { "action": "compare_rerun", "prompt": "...", "slot": {...} }
        { "action": "compare_cancel" }

    Protocol (server → client):
        { "type": "compare_chunk",    "slot_id": N, "text": "..." }
        { "type": "compare_done",     "slot_id": N, "meta": {...} }
        { "type": "compare_error",    "slot_id": N, "text": "..." }
        { "type": "compare_all_done" }
    """
    config = websocket.app.state.config
    await websocket.accept()
    logger.info(f"Compare WS connected: {session_id}")

    active_tasks: Dict[int, asyncio.Task] = {}
    waiter_task: asyncio.Task | None = None

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            # ── Run all slots ──────────────────────────────────────────────
            if action == "compare":
                # Cancel any in-progress work
                if waiter_task and not waiter_task.done():
                    waiter_task.cancel()
                for t in active_tasks.values():
                    t.cancel()
                active_tasks.clear()

                prompt = data.get("prompt", "").strip()
                slots = data.get("slots", [])

                if not prompt:
                    await websocket.send_json({
                        "type": "compare_error",
                        "slot_id": -1,
                        "text": "Prompt is required.",
                    })
                    continue

                for slot_conf in slots:
                    sid = slot_conf.get("slot_id", 0)
                    task = asyncio.create_task(
                        _stream_slot(websocket, config, slot_conf, prompt)
                    )
                    active_tasks[sid] = task

                waiter_task = asyncio.create_task(
                    _await_all_and_signal(websocket, dict(active_tasks))
                )

            # ── Re-run a single slot ───────────────────────────────────────
            elif action == "compare_rerun":
                prompt = data.get("prompt", "").strip()
                slot_conf = data.get("slot", {})
                sid = slot_conf.get("slot_id", 0)

                # Cancel previous run for this slot if still active
                if sid in active_tasks and not active_tasks[sid].done():
                    active_tasks[sid].cancel()

                if prompt and slot_conf.get("model_id"):
                    task = asyncio.create_task(
                        _stream_slot(websocket, config, slot_conf, prompt)
                    )
                    active_tasks[sid] = task

            # ── Cancel everything ──────────────────────────────────────────
            elif action == "compare_cancel":
                if waiter_task and not waiter_task.done():
                    waiter_task.cancel()
                for t in active_tasks.values():
                    t.cancel()
                active_tasks.clear()
                await websocket.send_json({"type": "compare_all_done"})

    except WebSocketDisconnect:
        logger.info(f"Compare WS disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Compare WS error: {e}")
        try:
            await websocket.send_json({"type": "compare_error", "slot_id": -1, "text": str(e)})
        except Exception:
            pass
    finally:
        # Cleanup any remaining tasks
        if waiter_task and not waiter_task.done():
            waiter_task.cancel()
        for t in active_tasks.values():
            t.cancel()
