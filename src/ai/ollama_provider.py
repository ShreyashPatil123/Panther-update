"""Ollama Provider — local LLM inference via Ollama REST API.

Supports chat completion, streaming, vision (LLaVA / Phi-3-Vision),
and tool/function calling for automation tasks.

Architecture reference: §4.1
"""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from loguru import logger


class OllamaProvider:
    """Async client for Ollama's local REST API (OpenAI-compatible)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        vision_model: str = "llava:13b",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.vision_model = vision_model
        self.client = httpx.AsyncClient(timeout=timeout)

    # ── Chat completion ──────────────────────────────────────────────────

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.1,
        num_ctx: int = 8192,
        top_p: float = 0.9,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request (non-streaming).

        Returns an OpenAI-compatible response dict with choices[].
        """
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "top_p": top_p,
            },
        }
        if tools:
            payload["tools"] = tools

        response = await self.client.post(
            f"{self.base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()

        # Normalise Ollama response → OpenAI-compatible shape
        return self._normalise_response(raw)

    # ── Streaming chat ───────────────────────────────────────────────────

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.1,
    ) -> AsyncIterator[str]:
        """Yield content chunks from a streaming chat response."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        async with self.client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not chunk.get("done"):
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content

    # ── Vision chat ──────────────────────────────────────────────────────

    async def chat_with_vision(
        self,
        messages: List[Dict[str, Any]],
        image_b64: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach a base64 screenshot to the last message for VLM inference."""
        messages = [dict(m) for m in messages]  # shallow copy
        messages[-1]["images"] = [image_b64]
        return await self.chat(messages, model=model or self.vision_model)

    # ── Health check ─────────────────────────────────────────────────────

    async def check_health(self) -> bool:
        """Return True if Ollama is reachable and serving models."""
        try:
            resp = await self.client.get(
                f"{self.base_url}/api/tags", timeout=3
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ── Available models ─────────────────────────────────────────────────

    async def list_models(self) -> List[str]:
        """Return model names currently available on the Ollama server."""
        try:
            resp = await self.client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.warning(f"[OllamaProvider] Failed to list models: {exc}")
            return []

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_response(raw: Dict) -> Dict:
        """Convert Ollama's native response into OpenAI-compatible format."""
        message = raw.get("message", {})
        tool_calls = message.get("tool_calls") or []

        choice: Dict[str, Any] = {
            "index": 0,
            "message": {
                "role": message.get("role", "assistant"),
                "content": message.get("content", ""),
            },
            "finish_reason": "stop",
        }
        if tool_calls:
            choice["message"]["tool_calls"] = tool_calls
            choice["finish_reason"] = "tool_calls"

        return {
            "id": f"ollama-{raw.get('created_at', '')}",
            "object": "chat.completion",
            "model": raw.get("model", ""),
            "choices": [choice],
            "usage": {
                "prompt_tokens": raw.get("prompt_eval_count", 0),
                "completion_tokens": raw.get("eval_count", 0),
                "total_tokens": (
                    raw.get("prompt_eval_count", 0) + raw.get("eval_count", 0)
                ),
            },
        }

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()
