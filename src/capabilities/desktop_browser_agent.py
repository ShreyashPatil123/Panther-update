"""Desktop Browser SubAgent — controls the user's ACTUAL browser.

Unlike the Playwright-based sub-agent, this one:
1. Opens new tabs in the user's existing Chrome/Edge
2. Uses PyAutoGUI for visible keyboard/mouse automation
3. Uses Gemini Flash for visual reasoning (screenshot → action)
4. The user SEES every action happening in their browser

Action flow: screenshot → Gemini plans → PyAutoGUI executes → repeat
"""

import asyncio
import base64
import json
import os
import re
from typing import AsyncGenerator, Dict, Optional

from loguru import logger

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from src.capabilities.desktop_browser import DesktopBrowserController


# ── Site map ─────────────────────────────────────────────────────────────────

SITE_MAP = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://twitter.com",
    "x.com": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "amazon": "https://www.amazon.com",
    "flipkart": "https://www.flipkart.com",
    "wikipedia": "https://www.wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
    "bing": "https://www.bing.com",
    "spotify": "https://open.spotify.com",
    "yt": "https://www.youtube.com",
    "fb": "https://www.facebook.com",
    "ig": "https://www.instagram.com",
    "netflix": "https://www.netflix.com",
    "ebay": "https://www.ebay.com",
    "pinterest": "https://www.pinterest.com",
    "quora": "https://www.quora.com",
    "medium": "https://medium.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "chatgpt": "https://chatgpt.com",
    "perplexity": "https://www.perplexity.ai",
    "npmjs": "https://www.npmjs.com",
    "pypi": "https://pypi.org",
}

# ── System prompt ────────────────────────────────────────────────────────────

DESKTOP_AGENT_PROMPT = """You are PANTHER's Desktop Browser Agent. You control the user's ACTUAL browser using keyboard and mouse automation.

You see a screenshot of the browser each turn. You decide the next action.

ACTIONS — return exactly ONE JSON action:

Navigation:
  {"action": "new_tab_navigate", "params": {"url": "https://..."}}  → Opens new tab and goes to URL
  {"action": "navigate", "params": {"url": "https://..."}}  → Navigate current tab to URL
  {"action": "go_back"}  → Go back in history
  {"action": "close_tab"}  → Close current tab
  {"action": "switch_tab", "params": {"direction": "next"}}  → Switch tabs (next/prev)

Interaction:
  {"action": "click_at", "params": {"x": 500, "y": 300, "description": "search button"}}  → Click at coordinates
  {"action": "type_text", "params": {"text": "hello world"}}  → Type text at cursor
  {"action": "press_key", "params": {"key": "Enter"}}  → Press key (Enter, Tab, Escape, Backspace, etc.)
  {"action": "hotkey", "params": {"keys": ["ctrl", "l"]}}  → Press keyboard shortcut
  {"action": "search", "params": {"query": "search terms"}}  → Type in address bar (universal search)

Page:
  {"action": "scroll", "params": {"direction": "down", "amount": 3}}  → Scroll page
  {"action": "wait", "params": {"seconds": 2}}  → Wait for page to load

Completion:
  {"action": "done", "params": {"result": "Summary of what was accomplished"}}

COORDINATE TIPS:
- The screenshot is of the browser window only
- Address bar is usually at y=50-60
- Main content starts at y=100+
- Look at the screenshot carefully to identify clickable elements and their positions
- Click the CENTER of buttons/links, not the edge

RULES:
1. ALWAYS analyze the screenshot before choosing an action
2. To search on a site: click the search box → type query → press Enter
3. To navigate: use new_tab_navigate to open in a new tab
4. Provide exact x,y coordinates based on the screenshot
6. If you can't find an element, try scrolling down first
7. CRITICAL: If asked to 'open' a brand, acronym, or organization and you DO NOT know their exact official URL (like .gov.in, .org, etc.), DO NOT guess a .com domain. Instead, use the 'search' action to Google the name and click the official link in the results.

RESPONSE FORMAT — return ONLY this JSON:
{"reasoning": "what I see and what I will do", "action": "action_name", "params": {...}, "done": false}
"""


async def _extract_url(task: str, gemini_model=None) -> Optional[str]:
    """Extract URL from task text."""
    m = re.search(r'https?://[^\s,\'"]+', task)
    if m:
        return m.group(0)
    m = re.search(r'www\.[^\s,\'"]+', task)
    if m:
        return "https://" + m.group(0)
    m = re.search(
        r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(com|org|net|io|co|in|ai|dev|app|me|edu|gov))\b',
        task,
    )
    if m:
        return "https://" + m.group(1)
    task_lower = task.lower()
    for name, url in SITE_MAP.items():
        if re.search(rf'\b{re.escape(name)}\b', task_lower):
            return url
            
    # Try normalizing the task to see if a brand matches
    from src.utils.brand_normalizer import normalize_brand
    
    query = _extract_search_query(task)
    brand_to_check = query if query else task
    
    normalized = await normalize_brand(brand_to_check, gemini_model)
    if normalized and normalized != brand_to_check:
        for name, url in SITE_MAP.items():
            if re.search(rf'\b{re.escape(name)}\b', normalized.lower()):
                return url
                
    return None


def _extract_search_query(task: str) -> Optional[str]:
    """Extract search query from task."""
    
    # AI models sometimes append rambling thoughts (e.g. "I'll do that now.").
    # Strip everything after the first period, newline or question mark to isolate the command.
    import re
    first_sentence_match = re.split(r'[.\n!]', task)
    clean_task = first_sentence_match[0].strip() if first_sentence_match else task

    patterns = [
        r'(?:open|go\s+to)\s+(.+)',
        r'(?:and|then)\s+(?:search|look|find)\s+(?:for\s+|about\s+)?(.+)',
        r'search\s+(?:for\s+|about\s+)?["\']?(.+?)["\']?\s+(?:on|in|at)\s+\S+',
        r'search\s+(?:for\s+|about\s+)(.+)',
        r'(?:find|look\s+(?:for|up))\s+(.+?)(?:\s+on\s+|\s*$)',
    ]
    for p in patterns:
        m = re.search(p, clean_task, re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            for name in SITE_MAP:
                q = re.sub(rf'\b{re.escape(name)}\b', '', q, flags=re.IGNORECASE).strip()
            # Strip trailing prepositions from end of query
            q = re.sub(r'\s+(?:on|in|at)\s*$', '', q, flags=re.IGNORECASE).strip()
            q = re.sub(r'\s+', ' ', q).strip().rstrip('.')
            # Remove quotes around queries explicitly if they were captured
            q = re.sub(r'^["\']|["\']$', '', q).strip()
            if q and len(q) > 1:
                return q
    return None


# ═══════════════════════════════════════════════════════════════════════════════


class DesktopBrowserSubAgent:
    """
    Sub-agent that controls the user's actual browser.
    Uses Gemini Flash for visual reasoning + PyAutoGUI for execution.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.browser = DesktopBrowserController()
        self.history: list = []
        self.max_steps = int(os.getenv("BROWSER_MAX_STEPS", "25"))

        # Configure Gemini
        self.model = None
        if genai and api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel("gemini-2.0-flash")
                logger.info("[DesktopAgent] Gemini initialized")
            except Exception as e:
                logger.error(f"[DesktopAgent] Gemini init failed: {e}")

    async def execute_task(
        self, task: str, context: Optional[dict] = None
    ) -> AsyncGenerator[dict, None]:
        """Main execution loop."""

        yield {"type": "plan", "message": f"🧠 Understanding task: {task}"}

        # ── Step 1: Find the browser ─────────────────────────────────────
        yield {"type": "action", "message": "🔍 Finding your browser..."}
        found = await self.browser._find_and_focus_browser()
        if not found:
            yield {"type": "error", "message": "❌ No browser window found. Please open Chrome or Edge."}
            return

        yield {"type": "action", "message": f"✅ Found {self.browser.browser_name}"}

        # ── Step 2: Pre-navigation ───────────────────────────────────────
        url = await _extract_url(task, self.model)
        query = _extract_search_query(task)

        if url:
            yield {"type": "action", "message": f"📑 Navigating to {url}"}
            await self.browser.navigate_to(url)
            yield {"type": "action", "message": f"✅ Navigated to {url}"}

        # ── Step 3: Search if needed ─────────────────────────────────────
        search_done = False
        if query and url:
            yield {"type": "action", "message": f"🔍 Searching for: {query}"}
            # Wait for page to fully load
            await asyncio.sleep(2.5)

            # Try to search natively using the known site URL
            search_done = await self.browser.tab_to_search_and_type(query, current_url=url)

            if search_done:
                await asyncio.sleep(2)
                yield {"type": "action", "message": "✅ Search submitted"}
            else:
                yield {"type": "action", "message": "⚠️ Couldn't find search box, using AI vision..."}
        elif query and not url:
            if "open" in task.lower() or "go to" in task.lower():
                import urllib.parse
                ducky_url = f"https://duckduckgo.com/?q=!ducky+{urllib.parse.quote(query)}"
                yield {"type": "action", "message": f"🍀 Feeling Lucky: {query}"}
                await self.browser.navigate_to(ducky_url)
                search_done = True
                yield {"type": "action", "message": "✅ Directed to DuckDuckGo"}
            else:
                # No specific site — just search in address bar (Google search)
                yield {"type": "action", "message": f"🔍 Searching Google for: {query}"}
                await self.browser.open_new_tab()
                await asyncio.sleep(0.3)
                await self.browser.focus_search_bar_and_search(query)
                search_done = True
                yield {"type": "action", "message": "✅ Google search submitted"}

        # ── Step 4: Gemini agent loop (for complex tasks) ────────────────
        if not self.model:
            # No Gemini — just take a screenshot and return
            screenshot = await self.browser.take_screenshot()
            yield {
                "type": "result",
                "message": "✅ Browser automated (no Gemini for further planning)",
                "data": {
                    "result": "Browser action complete. Check your browser.",
                    "screenshot": screenshot,
                },
            }
            return

        # If navigation + search both succeeded, summarize and finish
        if url and search_done:
            await asyncio.sleep(1)
            screenshot = await self.browser.take_screenshot()

            # Ask Gemini to summarize what's on screen
            summary = await self._summarize_screen(task, screenshot)

            yield {
                "type": "result",
                "message": "✅ Task complete",
                "data": {
                    "result": summary or "Browser action complete. Check your browser.",
                    "screenshot": screenshot,
                },
            }
            return

        # If we navigated but search failed, let Gemini handle it visually
        if url and query and not search_done:
            # Fall through to the Gemini agent loop below
            pass
        elif url and not query:
            # Just navigation, no search needed — summarize and finish
            await asyncio.sleep(1)
            screenshot = await self.browser.take_screenshot()
            summary = await self._summarize_screen(task, screenshot)
            yield {
                "type": "result",
                "message": "✅ Task complete",
                "data": {
                    "result": summary or "Browser action complete. Check your browser.",
                    "screenshot": screenshot,
                },
            }
            return

        # Complex task — full agent loop
        retries = 0
        for step in range(1, self.max_steps + 1):
            try:
                screenshot = await self.browser.take_screenshot()

                yield {
                    "type": "action",
                    "message": f"📸 Step {step}: Analyzing screen...",
                }

                plan = await self._ask_gemini(task, screenshot)

                if plan is None:
                    retries += 1
                    if retries >= 3:
                        yield {
                            "type": "result",
                            "message": "⚠️ Planning failed",
                            "data": {"result": "Could not plan further actions.", "screenshot": screenshot},
                        }
                        return
                    continue

                retries = 0

                if plan.get("done"):
                    result = plan.get("params", {}).get("result", "Task complete.")
                    yield {
                        "type": "result",
                        "message": "✅ Task complete",
                        "data": {"result": result, "screenshot": screenshot},
                    }
                    return

                action = plan.get("action", "")
                reasoning = plan.get("reasoning", "")
                yield {"type": "action", "message": f"🔄 Step {step}: {action} — {reasoning[:80]}"}

                ok = await self._execute(plan)
                if not ok:
                    retries += 1
                    if retries >= 3:
                        yield {
                            "type": "result",
                            "message": "⚠️ Actions failed",
                            "data": {"result": "Could not complete the action.", "screenshot": screenshot},
                        }
                        return
                else:
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[DesktopAgent] Step {step}: {e}")
                retries += 1
                if retries >= 3:
                    yield {
                        "type": "result",
                        "message": f"⚠️ Error: {e}",
                        "data": {"result": str(e)},
                    }
                    return

        yield {
            "type": "result",
            "message": f"⚠️ Max steps ({self.max_steps})",
            "data": {"result": "Maximum steps reached."},
        }

    # ── Gemini visual reasoning ──────────────────────────────────────────────

    async def _ask_gemini(self, task: str, screenshot_b64: str) -> Optional[dict]:
        """Send screenshot to Gemini and get next action plan."""
        if not self.model:
            return None

        history = ""
        for h in self.history[-6:]:
            history += f"  Step {h['step']}: {h['action']} — {h['reason'][:50]}\n"

        prompt = f"{DESKTOP_AGENT_PROMPT}\n\nUSER TASK: {task}\n"
        if history:
            prompt += f"\nACTION HISTORY:\n{history}\n"
        prompt += "\nAnalyze the screenshot and return your next action as JSON."

        try:
            if screenshot_b64 and len(screenshot_b64) > 100:
                import PIL.Image
                import io

                img = PIL.Image.open(io.BytesIO(base64.b64decode(screenshot_b64)))
                resp = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.model.generate_content([prompt, img])
                )
            else:
                resp = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.model.generate_content(prompt)
                )

            raw = resp.text.strip()
            logger.debug(f"[DesktopAgent] Gemini: {raw[:200]}")

            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            plan = json.loads(raw)
            self.history.append({
                "step": len(self.history) + 1,
                "action": plan.get("action", "?"),
                "reason": plan.get("reasoning", ""),
            })
            return plan

        except Exception as e:
            logger.error(f"[DesktopAgent] Gemini error: {e}")
            return None

    async def _summarize_screen(self, task: str, screenshot_b64: str) -> str:
        """Ask Gemini to summarize what's visible on screen."""
        if not self.model or not screenshot_b64:
            return ""

        try:
            import PIL.Image
            import io

            img = PIL.Image.open(io.BytesIO(base64.b64decode(screenshot_b64)))
            prompt = (
                f"The user asked: '{task}'\n\n"
                f"Look at this screenshot of their browser. "
                f"Summarize what you see — the page content, search results, etc. "
                f"Be concise and informative. If there are search results, list the top 3-5."
            )
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.model.generate_content([prompt, img])
            )
            return resp.text.strip()
        except Exception as e:
            logger.warning(f"[DesktopAgent] Summary failed: {e}")
            return ""

    # ── Action execution ─────────────────────────────────────────────────────

    async def _execute(self, plan: dict) -> bool:
        """Execute a planned action using PyAutoGUI."""
        action = plan.get("action", "")
        params = plan.get("params", {})

        try:
            if action == "new_tab_navigate":
                await self.browser.open_new_tab()
                await asyncio.sleep(0.3)
                await self.browser.navigate_to(params.get("url", ""))

            elif action == "navigate":
                await self.browser.navigate_to(params.get("url", ""))

            elif action == "go_back":
                await self.browser.go_back()

            elif action == "close_tab":
                await self.browser.close_tab()

            elif action == "switch_tab":
                await self.browser.switch_tab(params.get("direction", "next"))

            elif action == "click_at":
                x = params.get("x", 0)
                y = params.get("y", 0)

                # Adjust coordinates relative to browser window
                if self.browser.browser_hwnd:
                    from src.capabilities.desktop_browser import _get_window_rect
                    rect = _get_window_rect(self.browser.browser_hwnd)
                    if rect:
                        x += rect[0]
                        y += rect[1]

                await self.browser.click_at(x, y)

            elif action == "type_text":
                await self.browser.type_text(params.get("text", ""))

            elif action == "press_key":
                await self.browser.press_key(params.get("key", "Enter"))

            elif action == "hotkey":
                keys = params.get("keys", [])
                if keys:
                    await self.browser.hotkey(*keys)

            elif action == "search":
                await self.browser.focus_search_bar_and_search(params.get("query", ""))

            elif action == "scroll":
                await self.browser.scroll(
                    params.get("direction", "down"),
                    params.get("amount", 3),
                )

            elif action == "wait":
                await asyncio.sleep(min(params.get("seconds", 2), 10))

            elif action == "done":
                return True

            return True

        except Exception as e:
            logger.error(f"[DesktopAgent] Action '{action}' error: {e}")
            return False
