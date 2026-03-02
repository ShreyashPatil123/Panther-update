"""DOM Serializer — convert raw HTML into compact Markdown for LLM consumption.

Strips noise (scripts, styles, SVGs), preserves semantic structure
(headings, links, inputs, buttons, selects), and produces a clean
Markdown representation suitable for LLM context windows.

Architecture reference: §6.2
"""

import re
from typing import List

from loguru import logger

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    BeautifulSoup = None  # type: ignore
    logger.warning("[DOMSerializer] BeautifulSoup not installed — HTML→MD disabled")


class DOMSerializer:
    """Convert page HTML into compact Markdown."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "meta", "link"}
    BLOCK_TAGS = {
        "div", "section", "article", "main", "aside",
        "header", "footer", "nav",
    }
    HEADING_MAP = {
        "h1": "#", "h2": "##", "h3": "###",
        "h4": "####", "h5": "#####",
    }

    async def page_to_markdown(self, page) -> str:
        """Fetch the current page's HTML and convert to Markdown.

        Args:
            page: Playwright Page object

        Returns:
            Compact Markdown string of the page content
        """
        html = await page.content()
        return self.html_to_markdown(html)

    def html_to_markdown(self, html: str) -> str:
        """Convert raw HTML to compact Markdown.

        Args:
            html: Raw HTML string

        Returns:
            Markdown representation
        """
        if BeautifulSoup is None:
            return "[DOMSerializer] BeautifulSoup not available"

        soup = BeautifulSoup(html, "html.parser")

        # Remove noisy elements
        for tag in soup(list(self.SKIP_TAGS)):
            tag.decompose()

        lines: List[str] = []
        self._process_node(soup.body or soup, lines)
        text = "\n".join(lines)

        # Collapse excess whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _process_node(self, node, lines: List[str]):
        """Recursively convert a DOM node to Markdown lines."""
        if isinstance(node, NavigableString):
            text = node.strip()
            if text:
                lines.append(text)
            return

        tag = node.name
        if not tag or tag in self.SKIP_TAGS:
            return

        if tag in self.HEADING_MAP:
            text = node.get_text(strip=True)
            lines.append(f"\n{self.HEADING_MAP[tag]} {text}\n")

        elif tag == "a":
            href = node.get("href", "#")
            text = node.get_text(strip=True)
            lines.append(f"[{text}]({href})")

        elif tag == "input":
            input_type = node.get("type", "text")
            name = (
                node.get("name")
                or node.get("id")
                or node.get("placeholder", "")
            )
            value = node.get("value", "")
            lines.append(f"<INPUT type={input_type} name={name} value={value}>")

        elif tag == "button":
            lines.append(f"<BUTTON>{node.get_text(strip=True)}</BUTTON>")

        elif tag == "select":
            name = node.get("name") or node.get("id", "")
            options = [o.get_text(strip=True) for o in node.find_all("option")]
            lines.append(f"<SELECT name={name} options={options}>")

        elif tag in ("p", "li"):
            lines.append(node.get_text(strip=True))

        else:
            for child in node.children:
                self._process_node(child, lines)
