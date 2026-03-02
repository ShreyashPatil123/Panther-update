"""NVIDIA NIM Provider — cloud-accelerated LLM inference via NIM API.

Thin adapter matching the architecture's interface (§4.2).
Wraps the existing NVIDIAClient with router-compatible methods.
"""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from loguru import logger


class NIMProvider:
    """Async client for NVIDIA NIM API (OpenAI-compatible)."""

    BASE_URL = "https://integrate.api.nvidia.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "meta/llama-3.1-70b-instruct",
        vision_model: str = "moonshotai/kimi-k2.5",
        timeout: float = 180.0,
    ):
        self.api_key = api_key
        self.model = model
        self.vision_model = vision_model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=timeout)

    # ── Chat completion ──────────────────────────────────────────────────

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        top_p: float = 0.95,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request (non-streaming).

        Returns an OpenAI-compatible response dict.
        """
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await self.client.post(
            f"{self.BASE_URL}/chat/completions",
            headers=self.headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    # ── Streaming chat ───────────────────────────────────────────────────

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield content chunks from a streaming chat response."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
        }
        async with self.client.stream(
            "POST",
            f"{self.BASE_URL}/chat/completions",
            headers=self.headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_text():
                line = line.strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, IndexError):
                        continue

    # ── Vision chat ──────────────────────────────────────────────────────

    async def vision_chat(
        self,
        messages: List[Dict[str, Any]],
        image_url: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a vision-enabled chat request (NVLM / llama-3.2-90b-vision)."""
        messages = [dict(m) for m in messages]
        last = messages[-1]
        last["content"] = [
            {"type": "text", "text": last["content"]},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        return await self.chat(messages, model=model or self.vision_model)

    # ── Health check ─────────────────────────────────────────────────────

    async def check_health(self) -> bool:
        """Return True if NIM API is reachable and key is valid."""
        try:
            resp = await self.client.get(
                f"{self.BASE_URL}/models",
                headers=self.headers,
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()
