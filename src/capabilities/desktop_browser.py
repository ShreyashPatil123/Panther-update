"""Desktop Browser Controller — controls the user's ACTUAL browser.

Uses a hybrid approach:
1. PyAutoGUI for keyboard/mouse simulation (visible to the user)
2. win32gui/ctypes for window management (find/focus browser)
3. CDP (Chrome DevTools Protocol) for DOM access & screenshots

The user sees their real browser being automated — no separate Playwright window.
"""

import asyncio
import base64
import ctypes
import json
import os
import re
import subprocess
import time
import webbrowser
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from loguru import logger

try:
    import pyautogui

    pyautogui.FAILSAFE = True  # Move mouse to top-left corner to abort
    pyautogui.PAUSE = 0.05  # Small pause between actions
except ImportError:
    pyautogui = None
    logger.warning("pyautogui not installed")

try:
    import win32gui
    import win32con
    import win32process
except ImportError:
    win32gui = None
    logger.warning("pywin32 not installed")

try:
    import websocket
except ImportError:
    websocket = None
    logger.warning("websocket-client not installed")

try:
    import requests as http_requests
except ImportError:
    http_requests = None


# ═══════════════════════════════════════════════════════════════════════════════
# Window Management (ctypes + win32gui)
# ═══════════════════════════════════════════════════════════════════════════════


def _find_browser_windows() -> List[Tuple[int, str, str]]:
    """Find all visible browser windows. Returns [(hwnd, title, class_name)]."""
    if not win32gui:
        return []

    windows = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            # Chrome, Edge, Brave all use Chrome_WidgetWin
            if (
                "Chrome_WidgetWin" in cls
                or "Google Chrome" in title
                or "Microsoft Edge" in title
                or "Brave" in title
                or "Opera" in title
            ):
                windows.append((hwnd, title, cls))
        return True

    win32gui.EnumWindows(callback, None)
    return windows


def _bring_to_front(hwnd: int) -> bool:
    """Bring a window to the foreground."""
    if not win32gui:
        return False
    try:
        # If window is minimized, restore it
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # Use a trick to reliably set foreground window
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
        return True
    except Exception as e:
        logger.warning(f"[DesktopBrowser] Failed to bring to front: {e}")
        return False


def _get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Get window position: (left, top, right, bottom)."""
    if not win32gui:
        return None
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# CDP Connection (Chrome DevTools Protocol)
# ═══════════════════════════════════════════════════════════════════════════════


class CDPConnection:
    """Connect to Chrome/Edge via CDP for DOM access & screenshots."""

    def __init__(self, port: int = 9222):
        self.port = port
        self.ws = None
        self._cmd_id = 0

    def get_targets(self) -> List[dict]:
        """Get list of open tabs."""
        if not http_requests:
            return []
        try:
            r = http_requests.get(f"http://localhost:{self.port}/json", timeout=2)
            return r.json()
        except Exception:
            return []

    def connect_to_tab(self, tab_id: Optional[str] = None) -> bool:
        """Connect to a specific tab or the most recent one."""
        targets = self.get_targets()
        if not targets:
            return False

        target = None
        if tab_id:
            target = next((t for t in targets if t.get("id") == tab_id), None)
        if not target:
            # Pick the first page-type target
            target = next(
                (t for t in targets if t.get("type") == "page"), None
            )
        if not target:
            return False

        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            return False

        try:
            self.ws = websocket.create_connection(ws_url, timeout=5)
            # Enable needed domains
            self._send("DOM.enable")
            self._send("Runtime.enable")
            self._send("Page.enable")
            return True
        except Exception as e:
            logger.warning(f"[CDP] Connection failed: {e}")
            return False

    def _send(self, method: str, params: Optional[dict] = None) -> dict:
        """Send a CDP command and get the response."""
        self._cmd_id += 1
        cmd = {"id": self._cmd_id, "method": method}
        if params:
            cmd["params"] = params
        self.ws.send(json.dumps(cmd))
        # Read until we get our response
        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._cmd_id:
                return data
            # Skip events

    def evaluate_js(self, expression: str) -> Optional[str]:
        """Run JavaScript on the page and return the result."""
        try:
            result = self._send(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "returnByValue": True,
                },
            )
            return result.get("result", {}).get("result", {}).get("value")
        except Exception as e:
            logger.warning(f"[CDP] JS eval failed: {e}")
            return None

    def screenshot(self) -> str:
        """Take a screenshot, returns base64 PNG."""
        try:
            result = self._send(
                "Page.captureScreenshot", {"format": "png"}
            )
            return result.get("result", {}).get("data", "")
        except Exception:
            return ""

    def get_page_url(self) -> str:
        """Get current page URL via CDP."""
        url = self.evaluate_js("window.location.href")
        return url or ""

    def get_page_title(self) -> str:
        """Get page title."""
        title = self.evaluate_js("document.title")
        return title or ""

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# Desktop Browser Controller
# ═══════════════════════════════════════════════════════════════════════════════


class DesktopBrowserController:
    """
    Controls the user's ACTUAL browser using PyAutoGUI + CDP.

    The user sees their real browser being automated — keyboard shortcuts,
    mouse clicks, and typing are all visible, like a human is operating.
    """

    def __init__(self):
        self.browser_hwnd: Optional[int] = None
        self.browser_name: str = "Unknown"
        self.cdp: Optional[CDPConnection] = None
        self._cdp_port = 9222

    async def _find_and_focus_browser(self) -> bool:
        """Find the user's browser and bring it to the foreground."""
        windows = _find_browser_windows()
        if not windows:
            logger.info("[DesktopBrowser] No browser found, opening default...")
            webbrowser.open("about:blank")
            await asyncio.sleep(2)
            windows = _find_browser_windows()

        if windows:
            self.browser_hwnd = windows[0][0]
            title = windows[0][1]
            if "Chrome" in title:
                self.browser_name = "Chrome"
            elif "Edge" in title:
                self.browser_name = "Edge"
            elif "Brave" in title:
                self.browser_name = "Brave"
            else:
                self.browser_name = "Browser"
            _bring_to_front(self.browser_hwnd)
            logger.info(f"[DesktopBrowser] Found: {self.browser_name} ({title[:50]})")
            return True

        logger.error("[DesktopBrowser] No browser window found")
        return False

    async def _try_cdp_connect(self) -> bool:
        """Try to connect to the browser via CDP."""
        self.cdp = CDPConnection(self._cdp_port)
        targets = self.cdp.get_targets()
        if targets:
            return self.cdp.connect_to_tab()
        return False

    # ─── PyAutoGUI Actions ────────────────────────────────────────────────

    async def open_new_tab(self):
        """Open a new blank tab using Ctrl+T. User sees the new tab appear."""
        if not pyautogui:
            return
        if self.browser_hwnd:
            _bring_to_front(self.browser_hwnd)
            await asyncio.sleep(0.3)
        pyautogui.hotkey("ctrl", "t")
        await asyncio.sleep(0.8)
        logger.info("[DesktopBrowser] Opened new tab (Ctrl+T)")

    async def navigate_current_tab(self, url: str):
        """Navigate the CURRENT tab to a URL using Ctrl+L → paste → Enter.

        Does NOT open a new tab — just changes the URL in the active tab.
        Uses clip.exe for reliable URL pasting.
        """
        if not pyautogui or not url:
            return
        if self.browser_hwnd:
            _bring_to_front(self.browser_hwnd)
            await asyncio.sleep(0.2)

        # Focus address bar
        pyautogui.hotkey("ctrl", "l")
        await asyncio.sleep(0.4)

        # Select all existing text
        pyautogui.hotkey("ctrl", "a")
        await asyncio.sleep(0.15)

        # Paste URL via clip.exe
        await self._clipboard_paste(url)
        await asyncio.sleep(0.3)

        # Press Enter to navigate
        pyautogui.press("enter")
        logger.info(f"[DesktopBrowser] Navigating current tab to: {url[:60]}")
        await asyncio.sleep(3)  # Wait for page load

    async def navigate_to(self, url: str):
        """Open a NEW tab and navigate to the URL.

        This is the main method for "go to website X" tasks.
        1. Opens a new tab (Ctrl+T) — visible to user
        2. Types the URL in the address bar — visible to user
        3. Presses Enter — visible to user
        """
        if not url:
            return
        await self.open_new_tab()
        await self.navigate_current_tab(url)

    async def type_text(self, text: str, use_clipboard: bool = True):
        """Type text. Uses clip.exe for reliability."""
        if not pyautogui:
            return

        if use_clipboard or any(ord(c) > 127 for c in text) or len(text) > 20:
            await self._clipboard_paste(text)
        else:
            pyautogui.typewrite(text, interval=0.03)

        await asyncio.sleep(0.2)

    async def _clipboard_paste(self, text: str):
        """Set clipboard using clip.exe (built into Windows) and paste.

        clip.exe is:
        - Synchronous (no timing issues)
        - Built into Windows 10/11
        - Handles all Unicode characters
        - Much more reliable than ctypes clipboard
        """
        text = text.strip()
        try:
            # Use clip.exe to set clipboard — synchronous and reliable
            process = subprocess.run(
                ["clip.exe"],
                input=text.encode("utf-16le"),
                check=True,
                timeout=5,
            )
            await asyncio.sleep(0.1)  # Small delay to ensure clipboard is set
        except Exception as e:
            logger.warning(f"[DesktopBrowser] clip.exe failed: {e}, trying ctypes")
            # Fallback to ctypes
            try:
                import ctypes
                CF_UNICODETEXT = 13
                kernel32 = ctypes.windll.kernel32
                user32 = ctypes.windll.user32
                user32.OpenClipboard(0)
                user32.EmptyClipboard()
                data = text.encode("utf-16-le") + b"\x00\x00"
                h_mem = kernel32.GlobalAlloc(0x0042, len(data))
                ptr = kernel32.GlobalLock(h_mem)
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                user32.CloseClipboard()
                await asyncio.sleep(0.2)
            except Exception as e2:
                logger.error(f"[DesktopBrowser] ctypes clipboard also failed: {e2}")
                return

        # Paste from clipboard
        if pyautogui:
            pyautogui.hotkey("ctrl", "v")
            await asyncio.sleep(0.2)

    async def press_key(self, key: str):
        """Press a keyboard key."""
        if not pyautogui:
            return
        pyautogui.press(key)
        await asyncio.sleep(0.3)

    async def hotkey(self, *keys):
        """Press a keyboard shortcut."""
        if not pyautogui:
            return
        pyautogui.hotkey(*keys)
        await asyncio.sleep(0.3)

    async def click_at(self, x: int, y: int):
        """Click at screen coordinates."""
        if not pyautogui:
            return
        pyautogui.click(x, y)
        await asyncio.sleep(0.3)

    async def scroll(self, direction: str = "down", amount: int = 3):
        """Scroll the page."""
        if not pyautogui:
            return
        clicks = amount if direction == "down" else -amount
        pyautogui.scroll(-clicks)  # Negative = scroll down
        await asyncio.sleep(0.3)

    async def take_screenshot(self) -> str:
        """Take screenshot using PyAutoGUI (whole screen or browser window)."""
        if not pyautogui:
            return ""
        try:
            if self.browser_hwnd:
                rect = _get_window_rect(self.browser_hwnd)
                if rect:
                    left, top, right, bottom = rect
                    img = pyautogui.screenshot(
                        region=(left, top, right - left, bottom - top)
                    )
                else:
                    img = pyautogui.screenshot()
            else:
                img = pyautogui.screenshot()

            import io

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.warning(f"[DesktopBrowser] Screenshot failed: {e}")
            return ""

    async def close_tab(self):
        """Close the current tab."""
        if not pyautogui:
            return
        pyautogui.hotkey("ctrl", "w")
        await asyncio.sleep(0.5)

    async def switch_tab(self, direction: str = "next"):
        """Switch to next/previous tab."""
        if not pyautogui:
            return
        if direction == "next":
            pyautogui.hotkey("ctrl", "tab")
        else:
            pyautogui.hotkey("ctrl", "shift", "tab")
        await asyncio.sleep(0.5)

    async def go_back(self):
        """Go back in browser history."""
        if not pyautogui:
            return
        pyautogui.hotkey("alt", "left")
        await asyncio.sleep(1)

    async def search_on_page(self, query: str):
        """Use Ctrl+F to search on the current page."""
        if not pyautogui:
            return
        pyautogui.hotkey("ctrl", "f")
        await asyncio.sleep(0.3)
        await self.type_text(query)
        await asyncio.sleep(0.2)
        pyautogui.press("enter")
        await asyncio.sleep(0.3)

    async def focus_search_bar_and_search(self, query: str):
        """
        Universal search: Focus address bar, type search query, press Enter.
        Works as Google search if no site search is available.
        """
        if not pyautogui:
            return

        # Try Tab key to find search box first (many sites)
        # But the most reliable universal approach is the address bar
        pyautogui.hotkey("ctrl", "l")
        await asyncio.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")
        await asyncio.sleep(0.1)

        # Type query
        await self.type_text(query)
        await asyncio.sleep(0.2)

        pyautogui.press("enter")
        await asyncio.sleep(2)

    async def tab_to_search_and_type(self, query: str, current_url: str = "") -> bool:
        """
        Search on the current site by navigating to the site's search URL.

        Strategy (in order of reliability):
        1. Detect the current site and use its known search URL pattern
        2. Fall back to typing in the address bar (uses Google as default)
        """
        if not pyautogui:
            return False

        # If current_url isn't provided, try to read it from the address bar (fallback)
        if not current_url:
            pyautogui.hotkey("ctrl", "l")
            await asyncio.sleep(0.3)
            pyautogui.hotkey("ctrl", "c")
            await asyncio.sleep(0.2)
            try:
                current_url = self._read_clipboard()
            except Exception:
                pass
            pyautogui.press("escape")
            await asyncio.sleep(0.2)

        # Known search URL patterns for major sites
        import urllib.parse
        encoded_query = urllib.parse.quote_plus(query)

        SEARCH_URLS = {
            "youtube.com": f"https://www.youtube.com/results?search_query={encoded_query}",
            "google.com": f"https://www.google.com/search?q={encoded_query}",
            "github.com": f"https://github.com/search?q={encoded_query}",
            "reddit.com": f"https://www.reddit.com/search/?q={encoded_query}",
            "amazon.com": f"https://www.amazon.com/s?k={encoded_query}",
            "amazon.in": f"https://www.amazon.in/s?k={encoded_query}",
            "flipkart.com": f"https://www.flipkart.com/search?q={encoded_query}",
            "wikipedia.org": f"https://en.wikipedia.org/wiki/Special:Search?search={encoded_query}",
            "stackoverflow.com": f"https://stackoverflow.com/search?q={encoded_query}",
            "bing.com": f"https://www.bing.com/search?q={encoded_query}",
            "twitter.com": f"https://twitter.com/search?q={encoded_query}",
            "x.com": f"https://x.com/search?q={encoded_query}",
            "ebay.com": f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}",
            "pinterest.com": f"https://www.pinterest.com/search/pins/?q={encoded_query}",
            "quora.com": f"https://www.quora.com/search?q={encoded_query}",
            "medium.com": f"https://medium.com/search?q={encoded_query}",
            "npmjs.com": f"https://www.npmjs.com/search?q={encoded_query}",
            "pypi.org": f"https://pypi.org/search/?q={encoded_query}",
            "spotify.com": f"https://open.spotify.com/search/{encoded_query}",
            "linkedin.com": f"https://www.linkedin.com/search/results/all/?keywords={encoded_query}",
            "perplexity.ai": f"https://www.perplexity.ai/search?q={encoded_query}",
        }

        # Match current URL to a known site
        search_url = None
        current_lower = current_url.lower()
        for domain, surl in SEARCH_URLS.items():
            if domain in current_lower:
                search_url = surl
                break

        if search_url:
            # Navigate the CURRENT tab to the search URL (don't open new tab)
            logger.info(f"[DesktopBrowser] Using search URL: {search_url[:60]}...")
            await self.navigate_current_tab(search_url)
            return True
        else:
            # Fallback: type query in address bar (will Google search it)
            logger.info("[DesktopBrowser] Unknown site, using address bar search")
            pyautogui.hotkey("ctrl", "l")
            await asyncio.sleep(0.3)
            pyautogui.hotkey("ctrl", "a")
            await asyncio.sleep(0.1)
            await self._clipboard_paste(query)
            await asyncio.sleep(0.3)
            pyautogui.press("enter")
            await asyncio.sleep(2)
            return True

    def _read_clipboard(self) -> str:
        """Read text from the Windows clipboard using ctypes."""
        import ctypes

        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard(0)
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                text = ctypes.wstring_at(ptr)
                return text
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    async def find_and_click_search_box(self) -> bool:
        """Legacy wrapper — use tab_to_search_and_type instead."""
        if not pyautogui:
            return False
        pyautogui.press("/")
        await asyncio.sleep(0.5)
        return True
