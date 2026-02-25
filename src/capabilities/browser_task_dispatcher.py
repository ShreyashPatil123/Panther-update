"""Task Dispatcher — coordinates between AgentOrchestrator and BrowserSubAgent.

Uses a dedicated thread + ProactorEventLoop for Playwright on Windows,
since uvicorn's SelectorEventLoop does not support subprocess transport.
"""

import asyncio
import logging
import os
import random
import sys
import threading
from typing import AsyncGenerator, Optional

from loguru import logger

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
    )
except ImportError:
    async_playwright = None  # type: ignore


# ── Stealth Script (injected on every page load) ─────────────────────────────

STEALTH_SCRIPT = """
// Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Fake plugin list (empty plugins = bot)
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ]
});

// Fake language list
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// Fix chrome object
window.chrome = {
  runtime: { onMessage: { addListener: () => {} } },
  loadTimes: function() {},
  csi: function() {},
  app: {}
};

// Normalize permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);
"""

# ── Random user agents ───────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PlaywrightThread — runs Playwright in its own asyncio loop on a background
# thread so it works inside uvicorn's SelectorEventLoop on Windows.
# ═══════════════════════════════════════════════════════════════════════════════

class _PlaywrightThread:
    """Manages a dedicated thread with a ProactorEventLoop for Playwright."""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> asyncio.AbstractEventLoop:
        """Start the background thread and return its event loop."""
        if self._loop is not None and self._loop.is_running():
            return self._loop

        ready = threading.Event()

        def _run():
            if sys.platform == "win32":
                self._loop = asyncio.ProactorEventLoop()
            else:
                self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True, name="playwright-loop")
        self._thread.start()
        ready.wait(timeout=5)
        return self._loop

    def run_coroutine(self, coro):
        """Schedule a coroutine on the Playwright loop and wait for the result."""
        if self._loop is None:
            self.start()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def run_coroutine_async(self, coro):
        """Schedule a coroutine on the Playwright loop, await from the calling loop."""
        if self._loop is None:
            self.start()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        # Bridge: await the concurrent.futures.Future from the calling loop
        return await asyncio.wrap_future(future)

    def stop(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None


# Module-level singleton
_pw_thread = _PlaywrightThread()


class TaskDispatcher:
    """
    Coordinates between AgentOrchestrator and BrowserSubAgent.
    Manages browser lifecycle and streams SSE progress events.

    All Playwright calls run on a dedicated ProactorEventLoop thread
    to avoid Windows SelectorEventLoop subprocess limitations.
    """

    def __init__(self, api_key: str, headless: Optional[bool] = None):
        self.api_key = api_key
        self.headless = headless if headless is not None else (
            os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
        )
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def _is_alive(self) -> bool:
        """Check if the browser page is still usable."""
        if not self._page or not self._browser:
            return False
        try:
            # Run a trivial check on the Playwright thread
            alive = await _pw_thread.run_coroutine_async(self._check_page())
            return alive
        except Exception:
            return False

    async def _check_page(self) -> bool:
        """Internal: check page liveness (runs on Playwright thread)."""
        try:
            if self._browser and not self._browser.is_connected():
                return False
            if self._page and self._page.is_closed():
                return False
            return True
        except Exception:
            return False

    async def initialize(self) -> None:
        """Launch Chromium on the dedicated Playwright thread."""
        if async_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        # Clean up any stale state first
        if self._playwright or self._browser:
            try:
                await self.close()
            except Exception:
                pass
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

        # Ensure the Playwright thread is running
        _pw_thread.start()

        # Run the actual Playwright launch on the dedicated loop
        await _pw_thread.run_coroutine_async(self._launch_browser())

        logger.info("[TaskDispatcher] Browser initialized (headless={})".format(
            self.headless
        ))

    async def _launch_browser(self) -> None:
        """Internal: launch browser (runs on the Playwright thread's loop)."""
        self._playwright = await async_playwright().start()

        launch_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1440,900",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=random.choice(USER_AGENTS),
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True,
            screen={"width": 1920, "height": 1080},
        )

        # Inject stealth scripts to hide automation fingerprints
        await self._context.add_init_script(STEALTH_SCRIPT)
        self._page = await self._context.new_page()

    async def dispatch(
        self,
        task: str,
        context_data: Optional[dict] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Dispatch a task to BrowserSubAgent and yield SSE events.
        This is the main entry point called by AgentOrchestrator.

        The BrowserSubAgent runs on the Playwright thread, and events
        are forwarded to the caller via an asyncio.Queue bridge.
        """
        # Check if browser is still alive, reinitialize if stale
        if not self._page or not await self._is_alive():
            logger.info("[TaskDispatcher] Browser not alive, (re)initializing...")
            await self.initialize()

        yield {"type": "plan", "message": f"🌐 Starting browser task: {task}"}

        # Run the sub-agent on the Playwright thread, bridging events via Queue
        event_queue: asyncio.Queue = asyncio.Queue()
        caller_loop = asyncio.get_event_loop()

        async def _run_subagent():
            try:
                from src.capabilities.extension_client import ExtensionRPCClient
                from src.capabilities.browser_subagent import BrowserSubAgent

                ext = ExtensionRPCClient(self._page)
                sub_agent = BrowserSubAgent(
                    api_key=self.api_key,
                    playwright_page=self._page,
                    extension_client=ext,
                )

                async for event in sub_agent.execute_task(task, context=context_data):
                    caller_loop.call_soon_threadsafe(event_queue.put_nowait, event)

            except Exception as e:
                logger.error(f"[TaskDispatcher] Sub-agent crashed: {e}")
                caller_loop.call_soon_threadsafe(
                    event_queue.put_nowait,
                    {"type": "error", "message": f"Browser sub-agent error: {e}"},
                )
            finally:
                caller_loop.call_soon_threadsafe(event_queue.put_nowait, None)

        # Start sub-agent on the Playwright thread
        pw_loop = _pw_thread.start()
        asyncio.run_coroutine_threadsafe(_run_subagent(), pw_loop)

        # Yield events as they arrive
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

    async def close(self) -> None:
        """Clean up browser resources."""
        try:
            if self._page or self._browser or self._playwright:
                await _pw_thread.run_coroutine_async(self._close_browser())
        except Exception as e:
            logger.warning(f"[TaskDispatcher] Cleanup error: {e}")

    async def _close_browser(self) -> None:
        """Internal: close browser (runs on the Playwright thread's loop)."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"[TaskDispatcher] Close error: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
