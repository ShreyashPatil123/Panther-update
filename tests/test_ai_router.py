"""Tests for AIRouter."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.ai.ai_router import AIRouter, ProviderStrategy


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _mock_response(content="OK"):
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    }


def _make_provider(healthy=True, response=None):
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=response or _mock_response())
    provider.check_health = AsyncMock(return_value=healthy)
    provider.close = AsyncMock()
    return provider


# ── Tests ────────────────────────────────────────────────────────────────────


class TestAIRouter:
    @pytest.mark.asyncio
    async def test_local_first_uses_ollama(self):
        ollama = _make_provider(response=_mock_response("from_ollama"))
        nim = _make_provider()
        router = AIRouter(ollama=ollama, nim=nim, strategy=ProviderStrategy.LOCAL_FIRST)

        result = await router.route([{"role": "user", "content": "hi"}])

        assert result["choices"][0]["message"]["content"] == "from_ollama"
        ollama.chat.assert_awaited_once()
        nim.chat.assert_not_awaited()
        await router.close()

    @pytest.mark.asyncio
    async def test_local_first_fallback_to_nim(self):
        ollama = _make_provider()
        ollama.chat = AsyncMock(side_effect=Exception("Ollama down"))
        nim = _make_provider(response=_mock_response("from_nim"))
        router = AIRouter(ollama=ollama, nim=nim, strategy=ProviderStrategy.LOCAL_FIRST)

        result = await router.route([{"role": "user", "content": "hi"}])

        assert result["choices"][0]["message"]["content"] == "from_nim"
        await router.close()

    @pytest.mark.asyncio
    async def test_performance_always_uses_nim(self):
        ollama = _make_provider()
        nim = _make_provider(response=_mock_response("from_nim"))
        router = AIRouter(ollama=ollama, nim=nim, strategy=ProviderStrategy.PERFORMANCE)

        result = await router.route([{"role": "user", "content": "hi"}])

        assert result["choices"][0]["message"]["content"] == "from_nim"
        nim.chat.assert_awaited_once()
        ollama.chat.assert_not_awaited()
        await router.close()

    @pytest.mark.asyncio
    async def test_cloud_first_uses_nim(self):
        ollama = _make_provider()
        nim = _make_provider(response=_mock_response("from_nim"))
        router = AIRouter(ollama=ollama, nim=nim, strategy=ProviderStrategy.CLOUD_FIRST)

        result = await router.route([{"role": "user", "content": "hi"}])
        assert result["choices"][0]["message"]["content"] == "from_nim"
        await router.close()

    @pytest.mark.asyncio
    async def test_cloud_first_fallback_to_ollama(self):
        ollama = _make_provider(response=_mock_response("from_ollama"))
        nim = _make_provider()
        nim.chat = AsyncMock(side_effect=Exception("NIM down"))
        router = AIRouter(ollama=ollama, nim=nim, strategy=ProviderStrategy.CLOUD_FIRST)

        result = await router.route([{"role": "user", "content": "hi"}])
        assert result["choices"][0]["message"]["content"] == "from_ollama"
        await router.close()

    @pytest.mark.asyncio
    async def test_no_provider_raises(self):
        router = AIRouter(ollama=None, nim=None)
        with pytest.raises(RuntimeError, match="No AI provider available"):
            await router.route([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_cost_optimal_small_uses_local(self):
        ollama = _make_provider(response=_mock_response("local"))
        nim = _make_provider()
        router = AIRouter(ollama=ollama, nim=nim, strategy=ProviderStrategy.COST_OPTIMAL)

        # Short message → should use local
        result = await router.route([{"role": "user", "content": "hi"}])
        assert result["choices"][0]["message"]["content"] == "local"
        ollama.chat.assert_awaited_once()
        await router.close()

    def test_invalidate_health_cache(self):
        router = AIRouter()
        router._ollama_healthy = True
        router._nim_healthy = False
        router.invalidate_health_cache()
        assert router._ollama_healthy is None
        assert router._nim_healthy is None
