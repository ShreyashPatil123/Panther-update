"""AI Router — intelligent provider selection with fallback.

Routes inference requests to Ollama or NVIDIA NIM based on
configurable strategies and automatic health-check fallback.

Architecture reference: §4.3
"""

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


class ProviderStrategy(str, Enum):
    """Routing strategy for AI provider selection."""

    LOCAL_FIRST = "local_first"      # Try Ollama, fallback to NIM
    CLOUD_FIRST = "cloud_first"      # Try NIM, fallback to Ollama
    VISION_AUTO = "vision_auto"      # Route VLM tasks to best available
    COST_OPTIMAL = "cost_optimal"    # Balance latency vs. cost
    PERFORMANCE = "performance"      # Always use NIM for max quality


class AIRouter:
    """Routes inference requests to the best available provider.

    Supports automatic fallback, vision routing, and cost-optimised
    heuristics based on estimated token count.
    """

    def __init__(
        self,
        ollama=None,
        nim=None,
        strategy: ProviderStrategy = ProviderStrategy.LOCAL_FIRST,
    ):
        """Initialise the router.

        Args:
            ollama: OllamaProvider instance (or None if not available)
            nim: NIMProvider instance (or None if not available)
            strategy: Default routing strategy
        """
        self.ollama = ollama
        self.nim = nim
        self.strategy = strategy

        # Cache health status to avoid hammering endpoints
        self._ollama_healthy: Optional[bool] = None
        self._nim_healthy: Optional[bool] = None

    # ── Main routing entry point ─────────────────────────────────────────

    async def route(
        self,
        messages: List[Dict[str, Any]],
        requires_vision: bool = False,
        tools: Optional[List[Dict]] = None,
        strategy: Optional[ProviderStrategy] = None,
    ) -> Dict[str, Any]:
        """Route an inference request to the best provider.

        Args:
            messages: Conversation messages
            requires_vision: Whether the request needs VLM capabilities
            tools: Optional tool/function definitions
            strategy: Override the default strategy for this request

        Returns:
            OpenAI-compatible chat completion response dict
        """
        active_strategy = strategy or self.strategy

        # ── Vision routing (always prefers VLM-capable provider) ─────
        if requires_vision:
            return await self._route_vision(messages, tools)

        # ── Strategy-based routing ───────────────────────────────────
        if active_strategy == ProviderStrategy.LOCAL_FIRST:
            return await self._route_local_first(messages, tools)

        elif active_strategy == ProviderStrategy.CLOUD_FIRST:
            return await self._route_cloud_first(messages, tools)

        elif active_strategy == ProviderStrategy.PERFORMANCE:
            return await self._route_performance(messages, tools)

        elif active_strategy == ProviderStrategy.COST_OPTIMAL:
            return await self._route_cost_optimal(messages, tools)

        elif active_strategy == ProviderStrategy.VISION_AUTO:
            return await self._route_vision(messages, tools)

        # Fallback: try anything
        return await self._route_local_first(messages, tools)

    # ── Strategy implementations ─────────────────────────────────────────

    async def _route_local_first(
        self, messages: List[Dict], tools: Optional[List[Dict]]
    ) -> Dict:
        """Try Ollama first, fall back to NIM."""
        if self.ollama:
            try:
                return await asyncio.wait_for(
                    self.ollama.chat(messages, tools), timeout=30
                )
            except Exception as exc:
                logger.warning(f"[AIRouter] Ollama failed, falling back to NIM: {exc}")

        if self.nim:
            return await self.nim.chat(messages, tools)

        raise RuntimeError("No AI provider available")

    async def _route_cloud_first(
        self, messages: List[Dict], tools: Optional[List[Dict]]
    ) -> Dict:
        """Try NIM first, fall back to Ollama."""
        if self.nim:
            try:
                return await self.nim.chat(messages, tools)
            except Exception as exc:
                logger.warning(f"[AIRouter] NIM failed, falling back to Ollama: {exc}")

        if self.ollama:
            return await self.ollama.chat(messages, tools)

        raise RuntimeError("No AI provider available")

    async def _route_performance(
        self, messages: List[Dict], tools: Optional[List[Dict]]
    ) -> Dict:
        """Always use NIM for maximum quality."""
        if self.nim:
            return await self.nim.chat(messages, tools)

        logger.warning("[AIRouter] NIM unavailable in PERFORMANCE mode, using Ollama")
        if self.ollama:
            return await self.ollama.chat(messages, tools)

        raise RuntimeError("No AI provider available")

    async def _route_cost_optimal(
        self, messages: List[Dict], tools: Optional[List[Dict]]
    ) -> Dict:
        """Use local for short tasks, cloud for complex ones.

        Heuristic: estimate token count from message content length.
        Below 2000 tokens → local; above → cloud.
        """
        total_tokens_estimate = sum(
            len(str(m.get("content", ""))) for m in messages
        ) // 4

        if total_tokens_estimate < 2000 and self.ollama:
            try:
                return await asyncio.wait_for(
                    self.ollama.chat(messages, tools), timeout=30
                )
            except Exception:
                pass

        if self.nim:
            return await self.nim.chat(messages, tools)

        if self.ollama:
            return await self.ollama.chat(messages, tools)

        raise RuntimeError("No AI provider available")

    async def _route_vision(
        self, messages: List[Dict], tools: Optional[List[Dict]]
    ) -> Dict:
        """Route vision requests to the best VLM-capable provider."""
        if self.ollama and await self._check_ollama_health():
            try:
                return await self.ollama.chat(messages, tools)
            except Exception as exc:
                logger.warning(f"[AIRouter] Ollama vision failed: {exc}")

        if self.nim:
            return await self.nim.chat(messages, tools)

        raise RuntimeError("No VLM-capable provider available")

    # ── Health checks ────────────────────────────────────────────────────

    async def _check_ollama_health(self) -> bool:
        """Check and cache Ollama health status."""
        if self._ollama_healthy is None and self.ollama:
            self._ollama_healthy = await self.ollama.check_health()
        return self._ollama_healthy or False

    async def _check_nim_health(self) -> bool:
        """Check and cache NIM health status."""
        if self._nim_healthy is None and self.nim:
            self._nim_healthy = await self.nim.check_health()
        return self._nim_healthy or False

    def invalidate_health_cache(self):
        """Reset cached health states (call after provider config changes)."""
        self._ollama_healthy = None
        self._nim_healthy = None

    # ── Cleanup ──────────────────────────────────────────────────────────

    async def close(self):
        """Close all provider clients."""
        if self.ollama:
            await self.ollama.close()
        if self.nim:
            await self.nim.close()
