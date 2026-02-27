"""Browser Controller — main entry point for browser automation.

Delegates to TaskDispatcher + BrowserSubAgent (Playwright + Gemini Flash)
for human-like browser control with Bezier mouse curves, natural typing,
CAPTCHA solving, and AI-driven DOM intelligence.

Replaces the old PyAutoGUI-based DesktopBrowserSubAgent approach.
"""

import os
from typing import AsyncGenerator, Optional

from loguru import logger


# ── Singleton dispatcher ─────────────────────────────────────────────────────
_dispatcher = None


async def _get_dispatcher(api_key: str, cdp_url: str = ""):
    """Lazily initialise the shared TaskDispatcher singleton."""
    global _dispatcher
    if _dispatcher is None:
        from src.capabilities.browser_task_dispatcher import TaskDispatcher

        headless = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
        _dispatcher = TaskDispatcher(
            api_key=api_key,
            headless=headless,
            cdp_url=cdp_url or os.getenv("CDP_URL", "http://localhost:9222"),
        )
        await _dispatcher.initialize()
        logger.info("[BrowserController] TaskDispatcher initialized")
    return _dispatcher


class BrowserController:
    """
    Entry point for browser automation — called by AgentOrchestrator.

    Maintains the same interface (execute_task_stream / execute_task) for
    backward compatibility, but delegates to the Playwright-based
    TaskDispatcher + BrowserSubAgent pipeline under the hood.
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")

    async def execute_task_stream(
        self, task: str, context: Optional[dict] = None
    ) -> AsyncGenerator[dict, None]:
        """
        Execute a browser task and yield SSE progress events.
        This is called by AgentOrchestrator._handle_browser_task().
        """
        try:
            dispatcher = await _get_dispatcher(self.api_key)
            async for event in dispatcher.dispatch(task, context_data=context):
                yield event
        except Exception as e:
            logger.error(f"[BrowserController] Task failed: {e}")
            yield {
                "type": "error",
                "message": f"Browser automation error: {e}",
            }

    async def execute_task(
        self, task: str, context: Optional[dict] = None
    ) -> str:
        """Execute a browser task and return the final result as a string."""
        result_text = "Browser task completed."
        async for event in self.execute_task_stream(task, context):
            if event.get("type") == "result":
                data = event.get("data", {})
                result_text = data.get("result", result_text)
            elif event.get("type") == "error":
                result_text = f"Error: {event.get('message', 'Unknown error')}"
        return result_text

    async def shutdown(self):
        """Clean up browser resources."""
        global _dispatcher
        if _dispatcher is not None:
            try:
                await _dispatcher.close()
            except Exception as e:
                logger.warning(f"[BrowserController] Shutdown error: {e}")
            _dispatcher = None
            logger.info("[BrowserController] Shutdown complete")
