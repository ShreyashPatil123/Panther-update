"""SOM Annotator — Set-of-Marks screenshot annotation for VLM interaction.

Overlays numbered bounding boxes onto page screenshots so that
Vision-Language Models can reference elements by numeric label
rather than by XPath or CSS selector.

Architecture reference: §6.3
"""

import io
from typing import Any, Dict, List, Tuple

from loguru import logger

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None  # type: ignore
    logger.warning("[SOMAnnotator] Pillow not installed — SOM disabled")


class SOMAnnotator:
    """Annotate screenshots with numbered element bounding boxes."""

    # Badge styling
    BADGE_COLOR = (255, 50, 50, 200)
    BOX_COLOR = (255, 50, 50, 220)
    BOX_WIDTH = 2
    TEXT_COLOR = "white"

    async def annotate_screenshot(
        self, page
    ) -> Tuple[bytes, Dict[str, Dict[str, Any]]]:
        """Take a screenshot and overlay numbered labels on interactive elements.

        Args:
            page: Playwright Page object

        Returns:
            Tuple of (annotated PNG bytes, element_map) where element_map
            maps label strings ("1", "2", …) to element info dicts.
        """
        if Image is None:
            raise RuntimeError("Pillow is required for SOM annotation")

        screenshot = await page.screenshot(type="png")
        elements = await self._get_element_boxes(page)

        img = Image.open(io.BytesIO(screenshot)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        element_map: Dict[str, Dict[str, Any]] = {}

        for i, el in enumerate(elements):
            box = el["box"]
            x, y = box["x"], box["y"]
            w, h = box["width"], box["height"]
            label = str(i + 1)
            element_map[label] = el

            # Draw bounding box
            draw.rectangle(
                [x, y, x + w, y + h],
                outline=self.BOX_COLOR,
                width=self.BOX_WIDTH,
            )

            # Draw label badge above the element
            badge_x = x
            badge_y = max(0, y - 18)
            badge_w = len(label) * 9 + 6
            badge_h = 16

            draw.rectangle(
                [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                fill=self.BADGE_COLOR,
            )
            draw.text(
                (badge_x + 3, badge_y + 1),
                label,
                fill=self.TEXT_COLOR,
            )

        # Composite and export
        annotated = Image.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        annotated.save(buf, format="PNG")
        return buf.getvalue(), element_map

    async def _get_element_boxes(self, page) -> List[Dict[str, Any]]:
        """Evaluate JS in page to collect bounding boxes of interactive elements."""
        return await page.evaluate("""
            () => {
                const selectors = 'a, button, input, select, textarea, [role="button"], [onclick]';
                return Array.from(document.querySelectorAll(selectors))
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    })
                    .map(el => ({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || null,
                        text: el.innerText?.slice(0, 80) || el.value?.slice(0, 80) || '',
                        placeholder: el.placeholder || '',
                        href: el.href || null,
                        box: el.getBoundingClientRect().toJSON()
                    }));
            }
        """)
