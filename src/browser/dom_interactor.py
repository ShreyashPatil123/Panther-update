"""DOM Interactor — high-level browser element interaction.

Provides click, type, scroll, form-fill, hover, and drag-and-drop
with human-like delays and smart field detection.

Architecture reference: §5.3
"""

from typing import Dict, Optional, Tuple

from loguru import logger


class DOMInteractor:
    """Interact with page elements via Playwright locators."""

    def __init__(self, page):
        self.page = page

    # ── Click ────────────────────────────────────────────────────────────

    async def click(
        self,
        selector: Optional[str] = None,
        coordinates: Optional[Tuple[int, int]] = None,
        timeout: int = 5000,
    ):
        """Click an element by CSS selector or (x, y) coordinates.

        Args:
            selector: CSS selector for the target element
            coordinates: (x, y) pixel coordinates for a raw click
            timeout: Max wait time in ms for the element to appear
        """
        if selector:
            await self.page.locator(selector).first.click(timeout=timeout)
        elif coordinates:
            await self.page.mouse.click(coordinates[0], coordinates[1])
        else:
            raise ValueError("Either selector or coordinates must be provided")

    # ── Type ─────────────────────────────────────────────────────────────

    async def type_text(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        delay: int = 50,
    ):
        """Type text into an input element with human-like delay.

        Args:
            selector: CSS selector for the input
            text: Text to type
            clear_first: Whether to clear existing content first
            delay: Delay between keystrokes in ms
        """
        locator = self.page.locator(selector).first
        if clear_first:
            await locator.clear()
        await locator.type(text, delay=delay)

    # ── Scroll ───────────────────────────────────────────────────────────

    async def scroll(self, direction: str = "down", amount: int = 500):
        """Scroll the page in a given direction.

        Args:
            direction: 'up', 'down', 'left', or 'right'
            amount: Pixels to scroll
        """
        if direction in ("up", "down"):
            delta = amount if direction == "down" else -amount
            await self.page.evaluate(f"window.scrollBy(0, {delta})")
        else:
            delta = amount if direction == "right" else -amount
            await self.page.evaluate(f"window.scrollBy({delta}, 0)")

    # ── Wait ─────────────────────────────────────────────────────────────

    async def wait_for_element(
        self, selector: str, timeout: int = 10_000
    ):
        """Wait for an element to become visible."""
        await self.page.wait_for_selector(
            selector, timeout=timeout, state="visible"
        )

    # ── Read ─────────────────────────────────────────────────────────────

    async def get_element_text(self, selector: str) -> str:
        """Get the inner text of an element."""
        return await self.page.locator(selector).first.inner_text()

    # ── Form filling ─────────────────────────────────────────────────────

    async def fill_form(self, form_data: Dict[str, str]):
        """Fill a form with smart field detection.

        Handles text inputs, checkboxes, radio buttons, and select dropdowns.

        Args:
            form_data: Mapping of CSS selector → value
        """
        for field_selector, value in form_data.items():
            element = self.page.locator(field_selector).first
            element_type = await element.get_attribute("type")
            tag_name = await element.evaluate("el => el.tagName")

            if element_type in ("checkbox", "radio"):
                if value.lower() in ("true", "yes", "1"):
                    await element.check()
            elif tag_name == "SELECT":
                await element.select_option(label=value)
            else:
                await self.type_text(field_selector, value)

    # ── Hover ────────────────────────────────────────────────────────────

    async def hover_and_wait(self, selector: str, wait_ms: int = 500):
        """Hover over an element and wait for tooltip/dropdown."""
        await self.page.locator(selector).first.hover()
        await self.page.wait_for_timeout(wait_ms)

    # ── Drag and drop ────────────────────────────────────────────────────

    async def drag_and_drop(self, source: str, target: str):
        """Drag an element to a target element."""
        await self.page.drag_and_drop(source, target)
