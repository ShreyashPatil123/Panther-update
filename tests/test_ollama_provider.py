"""Tests for OllamaProvider."""

import json
import pytest
import httpx

from src.ai.ollama_provider import OllamaProvider


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ollama_response(content="Hello", role="assistant", model="llama3.2"):
    """Build a minimal Ollama-native response dict."""
    return {
        "model": model,
        "created_at": "2024-01-01T00:00:00Z",
        "message": {"role": role, "content": content},
        "done": True,
        "prompt_eval_count": 10,
        "eval_count": 5,
    }


def _ollama_tool_response():
    """Build an Ollama response with a tool call."""
    return {
        "model": "llama3.2",
        "created_at": "2024-01-01T00:00:00Z",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "navigate",
                        "arguments": json.dumps({"url": "https://google.com"}),
                    },
                }
            ],
        },
        "done": True,
    }


# ── Tests ────────────────────────────────────────────────────────────────────


class TestOllamaProvider:
    def test_init_defaults(self):
        p = OllamaProvider()
        assert p.base_url == "http://localhost:11434"
        assert p.model == "llama3.2"
        assert p.vision_model == "llava:13b"

    def test_init_custom(self):
        p = OllamaProvider(
            base_url="http://myhost:5000/",
            model="qwen2.5:7b",
        )
        assert p.base_url == "http://myhost:5000"  # trailing slash stripped
        assert p.model == "qwen2.5:7b"

    def test_normalise_response_basic(self):
        raw = _ollama_response("Hi there")
        result = OllamaProvider._normalise_response(raw)

        assert result["choices"][0]["message"]["content"] == "Hi there"
        assert result["choices"][0]["message"]["role"] == "assistant"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["total_tokens"] == 15

    def test_normalise_response_with_tool_calls(self):
        raw = _ollama_tool_response()
        result = OllamaProvider._normalise_response(raw)

        assert result["choices"][0]["finish_reason"] == "tool_calls"
        tc = result["choices"][0]["message"]["tool_calls"]
        assert len(tc) == 1
        assert tc[0]["function"]["name"] == "navigate"

    @pytest.mark.asyncio
    async def test_check_health_failure(self):
        """Health check returns False when server is unreachable."""
        p = OllamaProvider(base_url="http://127.0.0.1:99999")
        result = await p.check_health()
        assert result is False
        await p.close()

    @pytest.mark.asyncio
    async def test_list_models_failure(self):
        """list_models returns empty list when server is unreachable."""
        p = OllamaProvider(base_url="http://127.0.0.1:99999")
        models = await p.list_models()
        assert models == []
        await p.close()
