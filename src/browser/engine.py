"""Browser Engine — Playwright wrapper for headless/headful browser control.

Provides launch, navigation, screenshot, JS execution, and stealth
anti-detection in a clean async API.

Architecture reference: §5.1
"""

from typing import Dict, Optional

from loguru import logger
from playwright.async_api import (
    BrowserContext,
    Page,
    async_playwright,
)


class BrowserEngine:
    """High-level Playwright browser wrapper with stealth support."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def launch(
        self,
        headless: bool = True,
        stealth: bool = True,
        proxy: Optional[Dict] = None,
        viewport_width: int = 1280,
        viewport_height: int = 900,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
    ):
        """Launch a new browser instance.

        Args:
            headless: Run without visible window
            stealth: Inject anti-detection scripts
            proxy: Optional proxy config dict
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            user_agent: Browser user-agent string
        """
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ],
        )

        context_options: Dict = {
            "viewport": {"width": viewport_width, "height": viewport_height},
            "user_agent": user_agent,
            "locale": "en-US",
        }
        if proxy:
            context_options["proxy"] = proxy

        self.context = await self.browser.new_context(**context_options)

        if stealth:
            await self._inject_stealth_scripts()

        self.page = await self.context.new_page()
        logger.info(
            f"[BrowserEngine] Launched ({'headless' if headless else 'headful'})"
        )

    async def connect_cdp(self, cdp_url: str, stealth: bool = True):
        """Connect to an existing browser via Chrome DevTools Protocol.

        Args:
            cdp_url: CDP WebSocket endpoint URL
            stealth: Inject anti-detection scripts
        """
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect_over_cdp(cdp_url)
        self.context = self.browser.contexts[0] if self.browser.contexts else (
            await self.browser.new_context()
        )
        if stealth:
            await self._inject_stealth_scripts()
        self.page = self.context.pages[0] if self.context.pages else (
            await self.context.new_page()
        )
        logger.info(f"[BrowserEngine] Connected via CDP: {cdp_url}")

    async def close(self):
        """Clean up all browser resources."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as exc:
            logger.warning(f"[BrowserEngine] Close error: {exc}")
        finally:
            self.context = None
            self.browser = None
            self.playwright = None

    # ── Navigation ───────────────────────────────────────────────────────

    async def navigate(self, url: str, wait_until: str = "domcontentloaded"):
        """Navigate to a URL and wait for page to load."""
        await self.page.goto(url, wait_until=wait_until, timeout=30_000)

    # ── Page inspection ──────────────────────────────────────────────────

    async def screenshot(self, full_page: bool = False) -> bytes:
        """Take a PNG screenshot of the current page."""
        return await self.page.screenshot(full_page=full_page, type="png")

    async def execute_js(self, script: str, *args):
        """Execute JavaScript in the page context and return the result."""
        return await self.page.evaluate(script, *args)

    async def get_title(self) -> str:
        """Return the current page title."""
        return await self.page.title()

    @property
    def url(self) -> str:
        """Return the current page URL."""
        return self.page.url if self.page else ""

    # ── Stealth ──────────────────────────────────────────────────────────

    async def _inject_stealth_scripts(self):
        """Override automation detection fingerprints."""
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                ],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        """)
