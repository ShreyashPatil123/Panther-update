"""Human Behaviour Engine — wraps Playwright actions with human-like physics."""

import asyncio
import math
import random
from typing import Optional, Tuple

from loguru import logger

try:
    from playwright.async_api import Page
except ImportError:
    Page = None  # type: ignore


class HumanBehaviourEngine:
    """
    Wraps all Playwright actions with human-like physics and timing.
    Every cursor movement follows a Bezier curve. Every keystroke has
    a natural, slightly variable delay. Every scroll has inertia.
    """

    def __init__(self, page: "Page"):
        self.page = page
        self._cursor_x: float = 0
        self._cursor_y: float = 0

    import contextlib

    @contextlib.asynccontextmanager
    async def _allow_action(self):
        """Temporarily bypass the UI event blocker so agent actions succeed."""
        try:
            await self.page.evaluate("window.__panther_allow_next_action = true")
            yield
        finally:
            try:
                await self.page.evaluate("window.__panther_allow_next_action = false")
            except Exception:
                pass  # Ignore if page navigation occurred

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and pause like a human reading the page."""
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self._human_pause("after_navigate")

    # ── Click ─────────────────────────────────────────────────────────────────

    async def click(
        self, selector: str = "", double: bool = False,
        x: Optional[float] = None, y: Optional[float] = None,
    ) -> None:
        """Click an element with Bezier mouse movement and hover delay.
        
        If x/y are provided, skip selector resolution and click those coords directly.
        """
        if x is not None and y is not None:
            # Direct coordinate mode — bypass selector lookup
            target_x, target_y = float(x), float(y)
        else:
            # Selector mode — resolve element bounding box
            element = await self.page.wait_for_selector(selector, timeout=5000)
            if not element:
                raise ValueError(f"Element not found: {selector}")

            box = await element.bounding_box()
            if not box:
                raise ValueError(f"Element has no bounding box: {selector}")

            target_x = box["x"] + box["width"] * (0.3 + random.random() * 0.4)
            target_y = box["y"] + box["height"] * (0.3 + random.random() * 0.4)

        # Move mouse via Bezier curve
        await self._bezier_mouse_move(target_x, target_y)

        # Brief hover before clicking (humans don't click instantly)
        await asyncio.sleep(random.uniform(0.08, 0.25))

        # Trigger visual click ripple
        try:
            await self.page.evaluate(
                f"if(window.__showPantherClick) window.__showPantherClick({target_x}, {target_y})"
            )
        except Exception:
            pass  # Visual feedback is non-critical

        async with self._allow_action():
            if double:
                await self.page.mouse.dblclick(target_x, target_y)
            else:
                await self.page.mouse.click(target_x, target_y)

        await self._human_pause("after_click")

    # ── Type ──────────────────────────────────────────────────────────────────

    async def type_text(
        self, selector: str = "", text: str = "", clear_first: bool = True,
        x: Optional[float] = None, y: Optional[float] = None,
    ) -> None:
        """Type text with human rhythm.
        
        If x/y are provided, click those coordinates first instead of using selector.
        """
        # Focus the target field
        if x is not None and y is not None:
            await self.click(x=x, y=y)
        else:
            await self.click(selector)
        await asyncio.sleep(random.uniform(0.1, 0.3))

        async with self._allow_action():
            if clear_first:
                await self.page.keyboard.press("Control+a")
                await asyncio.sleep(random.uniform(0.05, 0.1))
                await self.page.keyboard.press("Delete")
                await asyncio.sleep(random.uniform(0.05, 0.15))

            # Type character by character with human rhythm
            wpm = random.uniform(55, 85)
            base_delay = 60 / (wpm * 5)  # Average seconds per character

            i = 0
            while i < len(text):
                char = text[i]

                # Occasional burst typing (humans type some words faster)
                burst = random.random() < 0.15
                if burst:
                    burst_end = min(i + random.randint(3, 8), len(text))
                    burst_text = text[i:burst_end]
                    await self.page.keyboard.type(burst_text)
                    await asyncio.sleep(random.uniform(base_delay * 0.6, base_delay))
                    i = burst_end
                    continue

                # Occasional typo and correction (2% chance)
                if random.random() < 0.02 and char.isalpha():
                    typo = chr(ord(char) + random.choice([-1, 1]))
                    await self.page.keyboard.type(typo)
                    await asyncio.sleep(random.uniform(0.1, 0.25))
                    await self.page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                await self.page.keyboard.type(char)

                # Variable inter-keystroke delay
                delay = base_delay + random.gauss(0, base_delay * 0.3)
                delay = max(0.03, min(delay, 0.4))  # Clamp to [30ms, 400ms]

                # Longer pause after punctuation (end of word/sentence)
                if char in (" ", ".", ",", "!", "?", "\n"):
                    delay *= random.uniform(1.5, 3.0)

                await asyncio.sleep(delay)
                i += 1

        await self._human_pause("after_type")

    # ── Scroll ────────────────────────────────────────────────────────────────

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        """Scroll with momentum simulation (multiple smaller steps)."""
        delta_y = amount if direction == "down" else -amount

        # Scroll in multiple smaller steps (momentum simulation)
        steps = random.randint(3, 7)

        async with self._allow_action():
            for i in range(steps):
                step_amount = delta_y / steps
                step_amount *= random.uniform(0.8, 1.2)  # Vary each step
                await self.page.mouse.wheel(0, step_amount)

                # Decreasing pause between steps (scroll slows down)
                pause = 0.05 * (1 + (i / steps))
                await asyncio.sleep(pause)

        # Brief pause after scrolling before next action
        await asyncio.sleep(random.uniform(0.2, 0.6))

    # ── Bezier Mouse Movement ─────────────────────────────────────────────────

    async def _bezier_mouse_move(
        self, target_x: float, target_y: float
    ) -> None:
        """Move mouse along a cubic Bezier curve with ease-in-out."""
        start_x, start_y = self._cursor_x, self._cursor_y

        dist = math.sqrt((target_x - start_x) ** 2 + (target_y - start_y) ** 2)
        if dist < 2:
            return

        # Perpendicular offset for curve midpoint (like a human arc)
        perp_x = -(target_y - start_y) / dist
        perp_y = (target_x - start_x) / dist
        curve_offset = random.uniform(-dist * 0.2, dist * 0.2)

        cp1_x = start_x + (target_x - start_x) * 0.25 + perp_x * curve_offset
        cp1_y = start_y + (target_y - start_y) * 0.25 + perp_y * curve_offset
        cp2_x = (
            start_x + (target_x - start_x) * 0.75 + perp_x * curve_offset * 0.5
        )
        cp2_y = (
            start_y + (target_y - start_y) * 0.75 + perp_y * curve_offset * 0.5
        )

        # Number of steps based on distance (more steps = smoother curve)
        steps = max(10, min(int(dist / 5), 60))
        speed_factor = random.uniform(0.6, 1.4)

        for i in range(steps + 1):
            t = i / steps
            # Ease-in-out curve: slow at start and end, fast in middle
            t_eased = t * t * (3 - 2 * t)

            x = (
                (1 - t_eased) ** 3 * start_x
                + 3 * (1 - t_eased) ** 2 * t_eased * cp1_x
                + 3 * (1 - t_eased) * t_eased ** 2 * cp2_x
                + t_eased ** 3 * target_x
            )
            y = (
                (1 - t_eased) ** 3 * start_y
                + 3 * (1 - t_eased) ** 2 * t_eased * cp1_y
                + 3 * (1 - t_eased) * t_eased ** 2 * cp2_y
                + t_eased ** 3 * target_y
            )

            # Move Playwright CDP mouse AND visual cursor concurrently
            await asyncio.gather(
                self.page.mouse.move(x, y),
                self.page.evaluate(
                    f"if(window.__movePantherCursor) window.__movePantherCursor({x:.1f}, {y:.1f})"
                ),
            )

            step_delay = (dist / (steps * 3000)) / speed_factor
            step_delay = max(0.002, step_delay)
            await asyncio.sleep(step_delay)

        self._cursor_x = target_x
        self._cursor_y = target_y

    # ── Pause Timing ──────────────────────────────────────────────────────────

    async def _human_pause(self, context: str = "generic") -> None:
        """Insert a human-like pause based on the action context."""
        timings = {
            "after_navigate": (0.8, 2.5),
            "after_click": (0.3, 0.9),
            "after_type": (0.2, 0.5),
            "between_steps": (0.5, 1.5),
            "reading": (1.0, 3.0),
        }
        lo, hi = timings.get(context, (0.2, 0.5))
        await asyncio.sleep(random.uniform(lo, hi))
