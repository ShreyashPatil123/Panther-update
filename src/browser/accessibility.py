"""Accessibility Tree Extractor — compact, numbered DOM for LLM consumption.

Extracts interactive elements from the Playwright accessibility tree
and formats them as a compact labeled string that LLMs can reason about.

Architecture reference: §6.1
"""

from typing import Any, Dict, List, Optional

from loguru import logger


class AccessibilityExtractor:
    """Extract and label interactive DOM elements from the accessibility tree."""

    INTERACTIVE_ROLES = {
        "button", "link", "textbox", "combobox", "checkbox",
        "radio", "listbox", "option", "menuitem", "tab", "searchbox",
    }

    def __init__(self, page):
        self.page = page

    async def get_interactive_elements(self) -> List[Dict[str, Any]]:
        """Extract all interactive elements from the accessibility tree.

        Returns:
            List of dicts with role, name, value, depth, checked, disabled, focused.
        """
        try:
            tree = await self.page.accessibility.snapshot(interesting_only=True)
        except Exception as exc:
            logger.warning(f"[AccessibilityExtractor] Snapshot failed: {exc}")
            return []

        elements: List[Dict] = []
        self._traverse(tree, elements)
        return elements

    def _traverse(
        self,
        node: Optional[Dict],
        result: List[Dict],
        depth: int = 0,
    ):
        """Recursively walk the accessibility tree and collect interactive nodes."""
        if not node:
            return

        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")

        if role in self.INTERACTIVE_ROLES and name:
            result.append({
                "role": role,
                "name": name,
                "value": value,
                "depth": depth,
                "checked": node.get("checked"),
                "disabled": node.get("disabled", False),
                "focused": node.get("focused", False),
            })

        for child in node.get("children", []):
            self._traverse(child, result, depth + 1)

    async def get_labeled_dom(self) -> str:
        """Return a compact, LLM-optimised labeled DOM string.

        Format:
            [0] button: "Search" [DISABLED]
            [1] textbox: "Query" value="hello"
            [2] link: "Home"

        Returns:
            Multi-line string of numbered interactive elements.
        """
        elements = await self.get_interactive_elements()
        lines = []
        for i, el in enumerate(elements):
            status = " [DISABLED]" if el["disabled"] else ""
            value_str = f' value="{el["value"]}"' if el["value"] else ""
            lines.append(
                f'[{i}] {el["role"]}: "{el["name"]}"{value_str}{status}'
            )
        return "\n".join(lines)

    async def get_element_count(self) -> int:
        """Return the number of interactive elements on the page."""
        elements = await self.get_interactive_elements()
        return len(elements)
