"""Action Executor — dispatches parsed LLM tool calls to the browser.

Maps action names to handler methods and returns structured
ActionResult objects for observation-driven loops.

Architecture reference: §7.2
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger


@dataclass
class ActionResult:
    """Result of a single browser action execution."""

    success: bool
    observation: str
    data: Any = None
    error: Optional[str] = None


class ActionExecutor:
    """Execute browser actions from parsed LLM tool calls.

    Each action is a method named ``_action_<name>`` that receives
    keyword arguments from the tool call parameters.
    """

    def __init__(self, browser, dom):
        """Initialise with BrowserEngine and DOMInteractor instances.

        Args:
            browser: BrowserEngine instance
            dom: DOMInteractor instance
        """
        self.browser = browser
        self.dom = dom

    async def execute(self, action_name: str, params: Dict) -> ActionResult:
        """Dispatch an action by name.

        Args:
            action_name: Name of the action (e.g. 'navigate', 'click')
            params: Dict of parameters for the action

        Returns:
            ActionResult with success status and observation text
        """
        handler = getattr(self, f"_action_{action_name}", None)
        if not handler:
            return ActionResult(
                success=False,
                observation="",
                error=f"Unknown action: {action_name}",
            )
        try:
            return await handler(**params)
        except Exception as exc:
            logger.error(f"[ActionExecutor] {action_name} failed: {exc}")
            return ActionResult(success=False, observation="", error=str(exc))

    # ── Action handlers ──────────────────────────────────────────────────

    async def _action_navigate(self, url: str) -> ActionResult:
        """Navigate to the given URL."""
        await self.browser.navigate(url)
        title = await self.browser.get_title()
        return ActionResult(
            success=True,
            observation=f"Navigated to {url}. Page title: '{title}'",
        )

    async def _action_click(
        self,
        selector: Optional[str] = None,
        som_label: Optional[int] = None,
        description: str = "",
        **_,
    ) -> ActionResult:
        """Click an element by CSS selector."""
        if selector:
            await self.dom.click(selector=selector)
            return ActionResult(
                success=True,
                observation=f"Clicked element: {selector}",
            )
        return ActionResult(
            success=False,
            observation="",
            error="No selector or SOM label provided",
        )

    async def _action_type(
        self,
        text: str,
        selector: Optional[str] = None,
        press_enter: bool = False,
    ) -> ActionResult:
        """Type text into an input element."""
        if selector:
            await self.dom.type_text(selector, text)
        else:
            await self.browser.page.keyboard.type(text, delay=40)

        if press_enter:
            await self.browser.page.keyboard.press("Enter")

        display = text[:50] + "..." if len(text) > 50 else text
        return ActionResult(
            success=True, observation=f"Typed: '{display}'"
        )

    async def _action_scroll(
        self, direction: str = "down", amount_px: int = 500
    ) -> ActionResult:
        """Scroll the page."""
        await self.dom.scroll(direction, amount_px)
        return ActionResult(
            success=True,
            observation=f"Scrolled {direction} by {amount_px}px",
        )

    async def _action_extract_data(
        self, fields: list, format: str = "json", **_
    ) -> ActionResult:
        """Extract data from the page (delegates to DOM serializer)."""
        from src.browser.dom_serializer import DOMSerializer

        dom_text = await DOMSerializer().page_to_markdown(self.browser.page)
        return ActionResult(
            success=True,
            observation="Data extracted",
            data={"dom": dom_text, "fields": fields},
        )

    async def _action_wait(
        self,
        condition: Optional[str] = None,
        duration_ms: int = 1000,
    ) -> ActionResult:
        """Wait for a condition or a fixed duration."""
        if condition:
            await self.dom.wait_for_element(condition)
            return ActionResult(
                success=True,
                observation=f"Element appeared: {condition}",
            )
        await self.browser.page.wait_for_timeout(duration_ms)
        return ActionResult(
            success=True, observation=f"Waited {duration_ms}ms"
        )

    async def _action_finish(
        self, result: str, data: Optional[Dict] = None
    ) -> ActionResult:
        """Signal task completion."""
        return ActionResult(success=True, observation=result, data=data)
