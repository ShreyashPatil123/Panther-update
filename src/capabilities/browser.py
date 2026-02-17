"""Browser automation with Playwright."""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

from loguru import logger


@dataclass
class BrowserConfig:
    """Browser configuration."""
    headless: bool = False
    user_data_dir: Optional[str] = None
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: Optional[str] = None
    proxy: Optional[str] = None
    extra_args: List[str] = None

    def __post_init__(self):
        if self.extra_args is None:
            self.extra_args = []


@dataclass
class PageSnapshot:
    """Snapshot of a page state."""
    url: str
    title: str
    html: str
    text: str
    screenshot: Optional[bytes] = None


class BrowserController:
    """Browser automation controller using Playwright."""

    def __init__(self, config: Optional[BrowserConfig] = None):
        """Initialize browser controller.

        Args:
            config: Browser configuration
        """
        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: Dict[str, Any] = {}
        self._page_counter = 0

        # Safety settings
        self._allowed_domains: List[str] = []
        self._blocked_domains: List[str] = []
        self._require_confirmation = True

    async def initialize(self):
        """Initialize Playwright browser."""
        logger.info("Initializing browser controller")

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # Launch browser
            browser_type = self._playwright.chromium

            # Build launch options
            launch_options = {
                "headless": self.config.headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ] + self.config.extra_args,
            }

            if self.config.proxy:
                launch_options["proxy"] = {"server": self.config.proxy}

            self._browser = await browser_type.launch(**launch_options)

            # Create browser context
            context_options = {
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                "accept_downloads": True,
            }

            if self.config.user_agent:
                context_options["user_agent"] = self.config.user_agent

            self._context = await self._browser.new_context(**context_options)

            logger.info("Browser controller initialized successfully")

        except ImportError:
            logger.error("Playwright not installed. Install with: pip install playwright")
            logger.error("Then run: playwright install chromium")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise

    async def create_page(self, page_id: Optional[str] = None) -> str:
        """Create a new browser page/tab.

        Args:
            page_id: Optional page identifier (auto-generated if not provided)

        Returns:
            Page ID
        """
        if not self._context:
            raise RuntimeError("Browser not initialized")

        if page_id is None:
            self._page_counter += 1
            page_id = f"page_{self._page_counter}"

        page = await self._context.new_page()

        # Set up event handlers
        page.on("dialog", lambda dialog: asyncio.create_task(self._handle_dialog(dialog)))
        page.on("download", lambda download: asyncio.create_task(self._handle_download(download)))

        self._pages[page_id] = page
        logger.info(f"Created new page: {page_id}")

        return page_id

    async def _handle_dialog(self, dialog):
        """Handle JavaScript dialogs."""
        logger.debug(f"Dialog appeared: {dialog.type} - {dialog.message}")
        await dialog.accept()

    async def _handle_download(self, download):
        """Handle file downloads."""
        logger.info(f"Download started: {download.suggested_filename}")
        # Save to downloads directory
        download_path = Path("./downloads") / download.suggested_filename
        download_path.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(download_path))
        logger.info(f"Download saved to: {download_path}")

    def _check_url_safety(self, url: str) -> bool:
        """Check if URL is allowed.

        Args:
            url: URL to check

        Returns:
            True if allowed, False otherwise
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Check blocked domains
            for blocked in self._blocked_domains:
                if blocked in domain:
                    logger.warning(f"URL blocked: {url}")
                    return False

            # If whitelist exists, check it
            if self._allowed_domains:
                for allowed in self._allowed_domains:
                    if allowed in domain:
                        return True
                logger.warning(f"URL not in whitelist: {url}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error checking URL safety: {e}")
            return False

    async def navigate(self, url: str, page_id: str = "main", wait_until: str = "networkidle") -> str:
        """Navigate to a URL.

        Args:
            url: URL to navigate to
            page_id: Page identifier
            wait_until: When to consider navigation complete

        Returns:
            Page title
        """
        if not self._check_url_safety(url):
            raise ValueError(f"URL not allowed: {url}")

        page = self._get_page(page_id)
        if not page:
            page_id = await self.create_page(page_id)
            page = self._pages[page_id]

        logger.info(f"Navigating to: {url}")
        await page.goto(url, wait_until=wait_until)
        title = await page.title()
        logger.info(f"Navigated to: {title}")

        return title

    async def click(self, selector: str, page_id: str = "main", timeout: int = 5000):
        """Click an element.

        Args:
            selector: CSS selector or XPath
            page_id: Page identifier
            timeout: Timeout in milliseconds
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        # Try to find element
        try:
            await page.click(selector, timeout=timeout)
            logger.info(f"Clicked element: {selector}")
        except Exception as e:
            logger.error(f"Failed to click {selector}: {e}")
            raise

    async def type_text(self, selector: str, text: str, page_id: str = "main", clear_first: bool = True):
        """Type text into an input field.

        Args:
            selector: CSS selector
            text: Text to type
            page_id: Page identifier
            clear_first: Whether to clear the field first
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        if clear_first:
            await page.fill(selector, text)
        else:
            await page.type(selector, text)

        logger.info(f"Typed text into: {selector}")

    async def press_key(self, key: str, page_id: str = "main"):
        """Press a keyboard key.

        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'Escape')
            page_id: Page identifier
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        await page.keyboard.press(key)
        logger.info(f"Pressed key: {key}")

    async def scroll(self, direction: str = "down", amount: int = 500, page_id: str = "main"):
        """Scroll the page.

        Args:
            direction: 'up' or 'down'
            amount: Pixels to scroll
            page_id: Page identifier
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        if direction == "down":
            await page.mouse.wheel(0, amount)
        else:
            await page.mouse.wheel(0, -amount)

        logger.info(f"Scrolled {direction} by {amount} pixels")

    async def get_text(self, selector: str, page_id: str = "main") -> str:
        """Get text content of an element.

        Args:
            selector: CSS selector
            page_id: Page identifier

        Returns:
            Text content
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        element = await page.query_selector(selector)
        if element:
            text = await element.inner_text()
            return text.strip()
        return ""

    async def get_html(self, selector: Optional[str] = None, page_id: str = "main") -> str:
        """Get HTML content.

        Args:
            selector: Optional CSS selector (entire page if None)
            page_id: Page identifier

        Returns:
            HTML content
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        if selector:
            element = await page.query_selector(selector)
            if element:
                return await element.inner_html()
            return ""
        else:
            return await page.content()

    async def get_all_links(self, page_id: str = "main") -> List[Dict[str, str]]:
        """Get all links on the page.

        Args:
            page_id: Page identifier

        Returns:
            List of link dictionaries
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        links = await page.eval_on_selector_all(
            "a[href]",
            """elements => elements.map(el => ({
                text: el.textContent.trim(),
                href: el.href
            }))"""
        )
        return links

    async def search_text(self, text: str, page_id: str = "main") -> bool:
        """Search for text on the page.

        Args:
            text: Text to search for
            page_id: Page identifier

        Returns:
            True if found
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        # Use Ctrl+F to find
        await page.keyboard.press("Control+f")
        await page.keyboard.type(text)

        # Check if found
        count = await page.eval_on_selector(
            "text=/" + text + "/i",
            "el => document.querySelectorAll(':contains('" + text + "')').length"
        )
        return count > 0

    async def wait_for_element(self, selector: str, timeout: int = 5000, page_id: str = "main"):
        """Wait for an element to appear.

        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds
            page_id: Page identifier
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        await page.wait_for_selector(selector, timeout=timeout)
        logger.info(f"Element appeared: {selector}")

    async def wait_for_load(self, page_id: str = "main", state: str = "networkidle"):
        """Wait for page to load.

        Args:
            page_id: Page identifier
            state: Load state to wait for
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        await page.wait_for_load_state(state)

    async def take_screenshot(self, page_id: str = "main", selector: Optional[str] = None, path: Optional[str] = None) -> bytes:
        """Take a screenshot.

        Args:
            page_id: Page identifier
            selector: Optional element selector (entire page if None)
            path: Optional path to save screenshot

        Returns:
            Screenshot bytes
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        if selector:
            element = await page.query_selector(selector)
            if element:
                screenshot = await element.screenshot(path=path)
            else:
                raise ValueError(f"Element not found: {selector}")
        else:
            screenshot = await page.screenshot(path=path, full_page=True)

        logger.info(f"Screenshot taken{' for ' + selector if selector else ''}")
        return screenshot

    async def get_snapshot(self, page_id: str = "main") -> PageSnapshot:
        """Get a snapshot of the current page state.

        Args:
            page_id: Page identifier

        Returns:
            Page snapshot
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        url = page.url
        title = await page.title()
        html = await page.content()

        # Extract main text content
        text = await page.eval_on_selector(
            "body",
            "el => el.innerText"
        )

        return PageSnapshot(
            url=url,
            title=title,
            html=html,
            text=text[:5000]  # Limit text length
        )

    async def execute_javascript(self, script: str, page_id: str = "main") -> Any:
        """Execute JavaScript on the page.

        Args:
            script: JavaScript code to execute
            page_id: Page identifier

        Returns:
            Script result
        """
        page = self._get_page(page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        result = await page.evaluate(script)
        return result

    async def close_page(self, page_id: str):
        """Close a specific page.

        Args:
            page_id: Page identifier
        """
        if page_id in self._pages:
            page = self._pages[page_id]
            await page.close()
            del self._pages[page_id]
            logger.info(f"Closed page: {page_id}")

    def _get_page(self, page_id: str) -> Any:
        """Get page by ID, creating if needed."""
        if page_id not in self._pages:
            # Auto-create main page
            if page_id == "main":
                return None  # Will be created on first use
            raise ValueError(f"Page {page_id} not found")
        return self._pages[page_id]

    async def set_allowed_domains(self, domains: List[str]):
        """Set allowed domains whitelist.

        Args:
            domains: List of allowed domains
        """
        self._allowed_domains = domains
        logger.info(f"Allowed domains: {domains}")

    async def set_blocked_domains(self, domains: List[str]):
        """Set blocked domains blacklist.

        Args:
            domains: List of blocked domains
        """
        self._blocked_domains = domains
        logger.info(f"Blocked domains: {domains}")

    async def shutdown(self):
        """Shutdown browser and cleanup."""
        logger.info("Shutting down browser controller")

        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self._pages.clear()
        logger.info("Browser controller shut down")


import asyncio
