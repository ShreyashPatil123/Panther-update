"""CDP Controller — low-level Chrome DevTools Protocol access.

Provides network interception, performance metrics, and full DOM
snapshots beyond what Playwright exposes natively.

Architecture reference: §5.2
"""

from typing import Any, Callable, Dict, Optional

from loguru import logger


class CDPController:
    """Direct CDP session interface for advanced browser control."""

    def __init__(self, page):
        self.page = page
        self._cdp = None

    async def get_cdp_session(self):
        """Create (or return cached) CDP session for the current page."""
        if self._cdp is None:
            self._cdp = await self.page.context.new_cdp_session(self.page)
        return self._cdp

    # ── Network interception ─────────────────────────────────────────────

    async def enable_network_interception(
        self, handler: Optional[Callable] = None
    ):
        """Capture and optionally modify network requests.

        Args:
            handler: Async callback for Fetch.requestPaused events.
                     If None, a default logging handler is used.
        """
        cdp = await self.get_cdp_session()
        await cdp.send("Network.enable")
        await cdp.send(
            "Fetch.enable", {"patterns": [{"requestStage": "Request"}]}
        )
        cdp.on("Fetch.requestPaused", handler or self._default_request_handler)
        logger.info("[CDPController] Network interception enabled")

    async def _default_request_handler(self, event: Dict):
        """Default handler: log and continue all requests."""
        request_id = event["requestId"]
        url = event["request"]["url"]
        logger.debug(f"[CDPController] Intercepted: {url[:120]}")
        cdp = await self.get_cdp_session()
        await cdp.send("Fetch.continueRequest", {"requestId": request_id})

    # ── Performance metrics ──────────────────────────────────────────────

    async def capture_performance_metrics(self) -> Dict[str, float]:
        """Collect browser performance metrics (LCP, FCP, etc.)."""
        cdp = await self.get_cdp_session()
        await cdp.send("Performance.enable")
        result = await cdp.send("Performance.getMetrics")
        return {m["name"]: m["value"] for m in result.get("metrics", [])}

    # ── DOM snapshot ─────────────────────────────────────────────────────

    async def get_dom_snapshot(self) -> Dict[str, Any]:
        """Full DOM snapshot including shadow DOM and computed styles."""
        cdp = await self.get_cdp_session()
        return await cdp.send(
            "DOMSnapshot.captureSnapshot",
            {
                "computedStyles": ["display", "visibility", "pointer-events"],
                "includeDOMRects": True,
                "includePaintOrder": True,
            },
        )

    # ── Cleanup ──────────────────────────────────────────────────────────

    async def close(self):
        """Detach the CDP session."""
        if self._cdp:
            try:
                await self._cdp.detach()
            except Exception:
                pass
            self._cdp = None
