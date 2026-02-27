"""Browser SubAgent — production-grade browser brain using Gemini Flash.

Inspired by:
- Claude Computer Use: screenshot-based visual reasoning loop
- browser-use library: numbered accessibility tree for LLM interaction
- Antigravity DOM access: semantic element resolution

Key features:
1. Numbered accessibility tree — LLM sees [1] button 'Search', says 'click [1]'
2. Multi-tab support — open_tab, switch_tab, close_tab actions
3. Universal search — generic search input detection for ANY site
4. Direct Playwright interaction — page.goto, page.fill, page.click
5. Graceful fallbacks — always returns page content on failure
"""

import asyncio
import base64
import json
import os
import re
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from loguru import logger
import aiohttp

try:
    import google.generativeai as genai
except ImportError:
    genai = None  # type: ignore


# ── System prompt ────────────────────────────────────────────────────────────

BROWSER_AGENT_PROMPT = """You are PANTHER's Browser Agent. You control a real Chromium browser.

EVERY TURN you get:
1. A screenshot of the current page
2. A numbered list of interactive elements (the accessibility tree)
3. Current page URL and title

ACTIONS — return exactly ONE JSON action per turn:

Navigation:
  {"action": "navigate", "params": {"url": "https://..."}}
  {"action": "go_back"}
  {"action": "open_tab", "params": {"url": "https://..."}}
  {"action": "switch_tab", "params": {"tab_index": 0}}
  {"action": "close_tab", "params": {"tab_index": 1}}

Interaction (use element index numbers from the accessibility tree):
  {"action": "click", "params": {"index": 5}}
  {"action": "type", "params": {"index": 3, "text": "hello world"}}
  {"action": "select", "params": {"index": 7, "value": "option_text"}}

Keyboard:
  {"action": "press_key", "params": {"key": "Enter"}}
  {"action": "press_key", "params": {"key": "Tab"}}
  {"action": "press_key", "params": {"key": "Escape"}}

Page:
  {"action": "scroll", "params": {"direction": "down", "amount": 500}}
  {"action": "wait", "params": {"seconds": 2}}
  {"action": "extract_text"}

Completion:
  {"action": "done", "params": {"result": "Summary of what was accomplished"}}

RULES:
1. ALWAYS reference elements by their [index] number from the tree
2. To search on a site: click the search input → type query → press Enter
3. If the search results are visible, extract them with done()
4. After each action, you will see the updated screenshot + tree
5. If an element you need isn't in the tree, try scrolling or waiting
6. Maximum 3 retries per action before trying alternative approach
7. When task is complete, ALWAYS use done() with a result summary

RESPONSE FORMAT — return ONLY this JSON, nothing else:
{"reasoning": "what I see and why I chose this action", "action": "action_name", "params": {...}, "done": false}
"""


# ── Site URL map ─────────────────────────────────────────────────────────────

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
    "spotify": "https://www.spotify.com",
    "netflix": "https://www.netflix.com",
    "ebay": "https://www.ebay.com",
    "pinterest": "https://www.pinterest.com",
    "quora": "https://www.quora.com",
    "medium": "https://www.medium.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "chatgpt": "https://chatgpt.com",
    "perplexity": "https://www.perplexity.ai",
    "npmjs": "https://www.npmjs.com",
    "pypi": "https://pypi.org",
    # Electronics / Tech
    "samsung": "https://www.samsung.com",
    "apple": "https://www.apple.com",
    "microsoft": "https://www.microsoft.com",
    "nvidia": "https://www.nvidia.com",
    "intel": "https://www.intel.com",
    "oneplus": "https://www.oneplus.com",
    "nothing": "https://nothing.tech",
    # Shopping
    "walmart": "https://www.walmart.com",
    "target": "https://www.target.com",
    "bestbuy": "https://www.bestbuy.com",
    "myntra": "https://www.myntra.com",
    "meesho": "https://www.meesho.com",
    "ajio": "https://www.ajio.com",
    # Social / Media
    "tiktok": "https://www.tiktok.com",
    "twitch": "https://www.twitch.tv",
    "discord": "https://discord.com",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    # Utilities
    "stackoverflow": "https://stackoverflow.com",
    "w3schools": "https://www.w3schools.com",
    "kaggle": "https://www.kaggle.com",
    "huggingface": "https://huggingface.co",
}


def _extract_url(task: str) -> Optional[str]:
    """Extract URL from task text."""
    # 1. Explicit URL
    m = re.search(r'https?://[^\s,\'"]+', task)
    if m:
        return m.group(0)
    m = re.search(r'www\.[^\s,\'"]+', task)
    if m:
        return "https://" + m.group(0)

    # 2. Domain pattern (e.g. samsung.com)
    m = re.search(r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(com|org|net|io|co|in|ai|dev|app|me|edu|gov))\b', task)
    if m:
        return "https://" + m.group(1)

    task_lower = task.lower()

    # 3. Fallback to None if not explicitly a URL structure. We will resolve via Perplexity if needed.
    return None

async def _resolve_url_via_perplexity(task: str, api_key: str) -> Optional[str]:
    """Use Perplexity API to intelligently resolve the official website domain from natural language."""
    if not api_key:
        return None
        
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "sonar",
        "messages": [
            {
                "role": "system",
                "content": "You are an expert at identifying official brand websites. Respond ONLY with valid JSON: {\"domain\": \"exact-root-domain.com\"}. Use web knowledge to find the canonical official site. Do not include www, paths, or explanations."
            },
            {
                "role": "user",
                "content": f"Extract the official website domain for: {task}"
            }
        ],
        "max_tokens": 50,
        "temperature": 0.1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=10) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        try:
                            parsed = json.loads(match.group())
                            domain = parsed.get("domain")
                            if domain:
                                if not domain.startswith("http"):
                                    return f"https://www.{domain.replace('www.', '')}"
                                return domain
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        logger.error(f"[SubAgent] Perplexity URL resolution failed: {e}")
        
    return None



def _extract_search_query(task: str) -> Optional[str]:
    """Extract search query from natural language."""
    patterns = [
        r'(?:and|then)\s+(?:search|look|find)\s+(?:for\s+|about\s+)?(.+)',
        r'search\s+(?:for\s+|about\s+)?["\']?(.+?)["\']?\s+(?:on|in|at)\s+\S+',
        r'search\s+(?:for\s+|about\s+)(.+)',
        r'(?:find|look\s+(?:for|up))\s+(.+?)(?:\s+on\s+|\s*$)',
    ]
    for p in patterns:
        m = re.search(p, task, re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            for name in SITE_MAP:
                pass # removed aggressive stripping

            q = re.sub(r'\s+', ' ', q).strip().rstrip('.')
            if q and len(q) > 1:
                return q
    return None


# ═══════════════════════════════════════════════════════════════════════════════


class BrowserSubAgent:
    """
    Production-grade browser agent with:
    - Numbered accessibility tree for precise LLM interaction
    - Multi-tab management
    - Universal search on any website
    - Gemini Flash visual reasoning
    """

    def __init__(self, api_key: str, playwright_page, extension_client):
        self.api_key = api_key
        self.page = playwright_page
        self.context = playwright_page.context  # Access to all tabs
        self.ext = extension_client
        self.history: list = []
        self.max_steps = int(os.getenv("BROWSER_MAX_STEPS", "25"))
        self._element_map: Dict[int, dict] = {}  # index → element info

        # Configure Gemini
        self.model = None
        if genai and api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel("gemini-2.0-flash")
                logger.info("[SubAgent] Gemini initialized")
            except Exception as e:
                logger.error(f"[SubAgent] Gemini init failed: {e}")

    # ── Main execution loop ──────────────────────────────────────────────────

    async def execute_task(
        self, task: str, context: Optional[dict] = None
    ) -> AsyncGenerator[dict, None]:
        yield {"type": "plan", "message": f"🧠 Understanding task: {task}"}

        # ── Pre-navigation ───────────────────────────────────────────────
        url = _extract_url(task)
        query = _extract_search_query(task)
        
        # If no explicit URL is found but the user wants to go to an official website or we have a query, ask Perplexity
        if not url and (re.search(r'\b(website|site|page)\b', task.lower()) or " on " in task.lower()):
            yield {"type": "action", "message": f"🌐 Resolving official website using Perplexity..."}
            # Look for perplexity key
            pplx_key = os.getenv("PERPLEXITY_API_KEY")
            resolved_url = await _resolve_url_via_perplexity(task, pplx_key)
            if resolved_url:
                url = resolved_url
                yield {"type": "action", "message": f"✨ Resolved to: {url}"}

        if url:
            yield {"type": "action", "message": f"🔗 Navigating to {url}"}
            try:
                await self._navigate(url)
                yield {"type": "action", "message": f"✅ Loaded: {self.page.url}"}
            except Exception as e:
                yield {"type": "error", "message": f"Navigation failed: {e}"}
                return

        # ── Quick search attempt ─────────────────────────────────────────
        if query:

            yield {"type": "action", "message": f"🔍 Searching: {query}"}
            searched = await self._universal_search(query)
            if searched:
                await asyncio.sleep(2.0)
                yield {"type": "action", "message": "✅ Search submitted"}

        # ── Google fallback: if still on about:blank, search Google ──────
        current = self.page.url
        if not current or current in ("about:blank", ""):
            google_query = query or task
            yield {"type": "action", "message": f"🔍 No target URL found, searching Google: {google_query}"}
            try:
                import urllib.parse
                google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(google_query)}"
                await self._navigate(google_url)
                yield {"type": "action", "message": f"✅ Google search loaded"}
            except Exception as e:
                yield {"type": "error", "message": f"Google fallback failed: {e}"}
                return

        # ── Main agent loop ──────────────────────────────────────────────
        retries = 0

        for step in range(1, self.max_steps + 1):
            try:
                # Build accessibility tree + screenshot
                tree_text, element_map = await self._build_accessibility_tree()
                self._element_map = element_map
                screenshot_b64 = await self._screenshot()
                tabs_info = await self._get_tabs_info()

                state_summary = (
                    f"URL: {self.page.url}\n"
                    f"Title: {await self.page.title()}\n"
                    f"Tabs: {tabs_info}\n"
                    f"\nInteractive Elements:\n{tree_text or '(no interactive elements found)'}"
                )

                yield {
                    "type": "action",
                    "message": f"📸 Step {step}: Analyzing page... ({len(element_map)} elements found)",
                }

                # No Gemini? Extract and return
                if not self.model:
                    text = await self._extract_text()
                    yield {
                        "type": "result",
                        "message": "✅ Done (no Gemini for planning)",
                        "data": {
                            "result": text[:3000] or "Page loaded.",
                            "final_url": self.page.url,
                            "steps_taken": step,
                        },
                    }
                    return

                # Ask Gemini
                plan = await self._ask_gemini(task, state_summary, screenshot_b64)

                if plan is None:
                    retries += 1
                    if retries >= 3:
                        text = await self._extract_text()
                        yield {
                            "type": "result",
                            "message": "⚠️ Planning failed, returning page content",
                            "data": {
                                "result": text[:3000] or "Planning failed.",
                                "final_url": self.page.url,
                                "steps_taken": step,
                            },
                        }
                        return
                    continue

                retries = 0

                # Done?
                if plan.get("done"):
                    result = plan.get("params", {}).get("result", "Task complete.")
                    yield {
                        "type": "result",
                        "message": "✅ Task complete",
                        "data": {
                            "result": result,
                            "screenshot": screenshot_b64,
                            "final_url": self.page.url,
                            "steps_taken": step,
                        },
                    }
                    return

                # Execute
                action_name = plan.get("action", "")
                reasoning = plan.get("reasoning", "")
                yield {
                    "type": "action",
                    "message": f"🔄 Step {step}: {action_name} — {reasoning[:80]}",
                }

                ok = await self._execute(plan)
                if not ok:
                    retries += 1
                    yield {"type": "action", "message": f"⚠️ Failed (retry {retries}/3)"}
                    if retries >= 3:
                        text = await self._extract_text()
                        yield {
                            "type": "result",
                            "message": "⚠️ Returning page content",
                            "data": {
                                "result": text[:3000] or "Actions failed.",
                                "final_url": self.page.url,
                                "steps_taken": step,
                            },
                        }
                        return
                else:
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[SubAgent] Step {step}: {e}")
                retries += 1
                if retries >= 3:
                    yield {
                        "type": "result",
                        "message": "⚠️ Errors, returning content",
                        "data": {
                            "result": await self._extract_text() or str(e),
                            "final_url": self.page.url,
                            "steps_taken": step,
                        },
                    }
                    return

        # Max steps
        yield {
            "type": "result",
            "message": f"⚠️ Max steps ({self.max_steps})",
            "data": {
                "result": await self._extract_text() or "Max steps reached.",
                "final_url": self.page.url,
                "steps_taken": self.max_steps,
            },
        }

    # ── Accessibility Tree ───────────────────────────────────────────────────

    async def _build_accessibility_tree(self) -> Tuple[str, Dict[int, dict]]:
        """
        Build a numbered list of interactive elements using Playwright's
        accessibility snapshot. This is what the LLM reasons about.

        Returns:
            (tree_text, element_map) where element_map maps index to element info
        """
        try:
            snapshot = await self.page.accessibility.snapshot()
        except Exception as e:
            logger.warning(f"[SubAgent] Accessibility snapshot failed: {e}")
            return await self._build_tree_fallback()

        if not snapshot:
            return await self._build_tree_fallback()

        elements: List[str] = []
        element_map: Dict[int, dict] = {}
        idx = [1]  # mutable counter

        INTERACTIVE_ROLES = {
            'button', 'link', 'textbox', 'searchbox', 'combobox',
            'checkbox', 'radio', 'slider', 'switch', 'menuitem',
            'tab', 'option', 'spinbutton', 'textarea',
        }

        def _walk(node: dict):
            role = node.get('role', '')
            name = (node.get('name', '') or '').strip()
            value = (node.get('value', '') or '').strip()

            if role in INTERACTIVE_ROLES:
                i = idx[0]
                label = name or value or '[unlabeled]'
                # Truncate long labels
                if len(label) > 60:
                    label = label[:57] + "..."
                display = f"[{i}] {role} '{label}'"
                if value and role in ('textbox', 'searchbox', 'combobox', 'textarea'):
                    display += f"  (value: '{value[:30]}')"
                elements.append(display)
                element_map[i] = {
                    "role": role,
                    "name": name,
                    "value": value,
                }
                idx[0] += 1

            for child in node.get('children', []):
                _walk(child)

        _walk(snapshot)

        # Cap at 50 elements to avoid overwhelming the LLM
        if len(elements) > 50:
            elements = elements[:50]
            elements.append(f"... ({idx[0] - 51} more elements, scroll to see)")

        return "\n".join(elements), element_map

    async def _build_tree_fallback(self) -> Tuple[str, Dict[int, dict]]:
        """Fallback: use JS to enumerate interactive elements."""
        try:
            items = await self.page.evaluate("""() => {
                const els = document.querySelectorAll(
                    'a, button, input, textarea, select, [role="button"], [role="link"], [role="searchbox"], [tabindex]'
                );
                return Array.from(els).slice(0, 50).map((el, i) => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    role: el.getAttribute('role') || '',
                    name: el.getAttribute('aria-label') || el.textContent?.trim()?.slice(0, 60) || el.placeholder || '',
                    value: el.value || '',
                }));
            }""")

            elements = []
            element_map = {}
            for i, item in enumerate(items, 1):
                role = item.get('role') or item.get('tag', '')
                if item.get('type'):
                    role = f"{role}[{item['type']}]"
                name = item.get('name', '[unlabeled]')
                display = f"[{i}] {role} '{name}'"
                elements.append(display)
                element_map[i] = item

            return "\n".join(elements), element_map
        except Exception:
            return "", {}

    # ── Multi-tab management ─────────────────────────────────────────────────

    async def _get_tabs_info(self) -> str:
        """Get info about all open tabs."""
        try:
            pages = self.context.pages
            tabs = []
            for i, p in enumerate(pages):
                marker = "→ " if p == self.page else "  "
                try:
                    title = await p.title()
                except Exception:
                    title = "unknown"
                tabs.append(f"{marker}[Tab {i}] {title} ({p.url[:60]})")
            return "\n".join(tabs)
        except Exception:
            return f"[Tab 0] {self.page.url}"

    async def _open_tab(self, url: str):
        """Open a new tab and switch to it."""
        new_page = await self.context.new_page()
        await new_page.goto(url, wait_until="domcontentloaded", timeout=15000)
        self.page = new_page
        logger.info(f"[SubAgent] Opened new tab: {url}")

    async def _switch_tab(self, index: int):
        """Switch to tab by index."""
        pages = self.context.pages
        if 0 <= index < len(pages):
            self.page = pages[index]
            await self.page.bring_to_front()
            logger.info(f"[SubAgent] Switched to tab {index}: {self.page.url}")
        else:
            logger.warning(f"[SubAgent] Invalid tab index: {index}")

    async def _close_tab(self, index: int):
        """Close a tab by index."""
        pages = self.context.pages
        if 0 <= index < len(pages) and len(pages) > 1:
            await pages[index].close()
            # Switch to the last remaining tab
            self.page = self.context.pages[-1]
            await self.page.bring_to_front()

    # ── Universal search ─────────────────────────────────────────────────────

    async def _universal_search(self, query: str) -> bool:
        """Find and use search input on ANY website."""
        strategies = [
            lambda: self.page.get_by_role("searchbox").first,
            lambda: self.page.get_by_placeholder(re.compile(r"search", re.IGNORECASE)).first,
            lambda: self.page.get_by_label(re.compile(r"search", re.IGNORECASE)).first,
            lambda: self.page.locator('input[type="search"]').first,
            lambda: self.page.locator('input[name="search_query"]').first,
            lambda: self.page.locator('input[name="q"]').first,
            lambda: self.page.locator('input[name="query"]').first,
            lambda: self.page.locator('input[name="search"]').first,
            lambda: self.page.locator('textarea[name="q"]').first,
            lambda: self.page.locator('input[id*="search" i]').first,
            lambda: self.page.locator('input[class*="search" i]').first,
            lambda: self.page.locator('input[aria-label*="search" i]').first,
            lambda: self.page.locator('[role="combobox"]').first,
            lambda: self.page.locator('input[placeholder*="search" i]').first,
            lambda: self.page.locator('input[placeholder*="find" i]').first,
            lambda: self.page.locator('input[placeholder*="query" i]').first,
        ]

        for get_el in strategies:
            try:
                el = get_el()
                if await el.is_visible(timeout=800):
                    await el.click(timeout=2000)
                    await asyncio.sleep(0.2)
                    await el.fill("")
                    await el.fill(query)
                    await asyncio.sleep(0.3)
                    await self.page.keyboard.press("Enter")
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        await asyncio.sleep(1.5)
                    return True
            except Exception:
                continue

        return False

    # ── Core helpers ─────────────────────────────────────────────────────────

    async def _navigate(self, url: str):
        if not url.startswith("http"):
            url = "https://" + url
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        try:
            await self.page.wait_for_load_state("load", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(0.5)

    async def _screenshot(self) -> str:
        try:
            data = await self.page.screenshot()
            return base64.b64encode(data).decode()
        except Exception:
            return ""

    async def _extract_text(self) -> str:
        try:
            return await self.page.evaluate(
                "() => document.body?.innerText?.slice(0, 5000) || ''"
            )
        except Exception:
            return ""

    # ── Gemini planning ──────────────────────────────────────────────────────

    async def _ask_gemini(
        self, task: str, state: str, screenshot_b64: str
    ) -> Optional[dict]:
        if not self.model:
            return None

        history = ""
        for h in self.history[-8:]:
            history += f"  Step {h['step']}: {h['action']} — {h['reason'][:50]}\n"

        prompt = (
            f"{BROWSER_AGENT_PROMPT}\n\n"
            f"USER TASK: {task}\n\n"
            f"CURRENT STATE:\n{state}\n"
        )
        if history:
            prompt += f"\nACTION HISTORY:\n{history}\n"
        prompt += "\nReturn your next action as JSON."

        try:
            if screenshot_b64 and len(screenshot_b64) > 100:
                import PIL.Image, io
                img = PIL.Image.open(io.BytesIO(base64.b64decode(screenshot_b64)))
                resp = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.model.generate_content([prompt, img])
                )
            else:
                resp = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.model.generate_content(prompt)
                )

            raw = resp.text.strip()
            logger.debug(f"[SubAgent] Gemini: {raw[:200]}")

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
            logger.error(f"[SubAgent] Gemini error: {e}")
            return None

    # ── Action execution ─────────────────────────────────────────────────────

    async def _execute(self, plan: dict) -> bool:
        action = plan.get("action", "")
        params = plan.get("params", {})

        try:
            if action == "navigate":
                await self._navigate(params.get("url", ""))

            elif action == "open_tab":
                await self._open_tab(params.get("url", "about:blank"))

            elif action == "switch_tab":
                await self._switch_tab(params.get("tab_index", 0))

            elif action == "close_tab":
                await self._close_tab(params.get("tab_index", 0))

            elif action == "click":
                idx = params.get("index")
                if idx and idx in self._element_map:
                    await self._click_by_index(idx)
                else:
                    # Fallback: try by intent text
                    intent = params.get("intent", "")
                    if intent:
                        await self._click_by_intent(intent)
                    else:
                        return False

            elif action == "type":
                idx = params.get("index")
                text = params.get("text", "")
                if idx and idx in self._element_map:
                    await self._type_by_index(idx, text)
                else:
                    field = params.get("field_intent", "")
                    if field:
                        await self._type_by_intent(field, text)
                    else:
                        return False

            elif action == "select":
                idx = params.get("index")
                value = params.get("value", "")
                if idx and idx in self._element_map:
                    info = self._element_map[idx]
                    sel = f'select:has([aria-label*="{info["name"]}" i])'
                    await self.page.select_option(sel, label=value, timeout=3000)

            elif action == "press_key":
                key = params.get("key", "Enter")
                await self.page.keyboard.press(key)
                await asyncio.sleep(0.5)

            elif action == "scroll":
                d = params.get("direction", "down")
                amt = params.get("amount", 500)
                delta = amt if d == "down" else -amt
                await self.page.mouse.wheel(0, delta)
                await asyncio.sleep(0.5)

            elif action == "wait":
                await asyncio.sleep(min(params.get("seconds", 2), 10))

            elif action == "extract_text":
                pass  # Handled in main loop

            elif action == "go_back":
                await self.page.go_back()
                await asyncio.sleep(1)

            elif action == "done":
                return True

            return True

        except Exception as e:
            logger.error(f"[SubAgent] Action '{action}' error: {e}")
            return False

    # ── Element interaction by index ─────────────────────────────────────────

    async def _click_by_index(self, idx: int) -> bool:
        """Click element by accessibility tree index."""
        info = self._element_map.get(idx, {})
        role = info.get("role", "")
        name = info.get("name", "")

        strategies = []
        if name:
            if role in ('button',):
                strategies.append(lambda: self.page.get_by_role("button", name=name, exact=False).first)
            elif role in ('link',):
                strategies.append(lambda: self.page.get_by_role("link", name=name, exact=False).first)
            elif role in ('tab',):
                strategies.append(lambda: self.page.get_by_role("tab", name=name, exact=False).first)
            elif role in ('menuitem',):
                strategies.append(lambda: self.page.get_by_role("menuitem", name=name, exact=False).first)

            # Generic strategies
            strategies.extend([
                lambda: self.page.get_by_text(name, exact=False).first,
                lambda: self.page.get_by_label(name, exact=False).first,
                lambda: self.page.get_by_title(name, exact=False).first,
                lambda: self.page.locator(f'[aria-label="{name}"]').first,
                lambda: self.page.locator(f'button:has-text("{name}")').first,
                lambda: self.page.locator(f'a:has-text("{name}")').first,
            ])

        # Try each strategy
        for get_el in strategies:
            try:
                el = get_el()
                if await el.is_visible(timeout=800):
                    await el.scroll_into_view_if_needed(timeout=2000)
                    await asyncio.sleep(0.1)
                    await el.click(timeout=3000)
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue

        # Last resort: use nth element in the accessibility order via JS
        try:
            all_interactive = await self.page.evaluate("""(idx) => {
                const els = document.querySelectorAll(
                    'a, button, input, textarea, select, [role="button"], [role="link"], [role="searchbox"], [tabindex]'
                );
                const el = els[idx - 1];
                if (el) { el.scrollIntoView({behavior: 'smooth', block: 'center'}); el.click(); return true; }
                return false;
            }""", idx)
            return all_interactive
        except Exception:
            return False

    async def _type_by_index(self, idx: int, text: str) -> bool:
        """Type text into element by accessibility tree index."""
        info = self._element_map.get(idx, {})
        name = info.get("name", "")

        strategies = []
        if name:
            strategies.extend([
                lambda: self.page.get_by_label(name, exact=False).first,
                lambda: self.page.get_by_placeholder(name, exact=False).first,
                lambda: self.page.get_by_role("textbox", name=name, exact=False).first,
                lambda: self.page.get_by_role("searchbox", name=name, exact=False).first,
            ])

        for get_el in strategies:
            try:
                el = get_el()
                if await el.is_visible(timeout=800):
                    await el.click(timeout=2000)
                    await asyncio.sleep(0.1)
                    await el.fill("")
                    await el.fill(text)
                    await asyncio.sleep(0.2)
                    return True
            except Exception:
                continue

        # JS fallback
        try:
            return await self.page.evaluate("""({idx, text}) => {
                const els = document.querySelectorAll('input, textarea, [role="textbox"], [role="searchbox"], [contenteditable="true"]');
                const el = els[idx - 1];
                if (el) {
                    el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    el.focus();
                    el.value = text;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    return true;
                }
                return false;
            }""", {"idx": idx, "text": text})
        except Exception:
            return False

    async def _click_by_intent(self, intent: str) -> bool:
        """Click element by natural language intent (fallback)."""
        strategies = [
            lambda: self.page.get_by_role("button", name=re.compile(intent, re.IGNORECASE)).first,
            lambda: self.page.get_by_role("link", name=re.compile(intent, re.IGNORECASE)).first,
            lambda: self.page.get_by_text(intent, exact=False).first,
            lambda: self.page.get_by_label(re.compile(intent, re.IGNORECASE)).first,
            lambda: self.page.locator(f'button:has-text("{intent}")').first,
            lambda: self.page.locator(f'a:has-text("{intent}")').first,
        ]
        for get_el in strategies:
            try:
                el = get_el()
                if await el.is_visible(timeout=800):
                    await el.click(timeout=3000)
                    return True
            except Exception:
                continue
        return False

    async def _type_by_intent(self, field_intent: str, text: str) -> bool:
        """Type into field by natural language intent (fallback)."""
        strategies = [
            lambda: self.page.get_by_label(re.compile(field_intent, re.IGNORECASE)).first,
            lambda: self.page.get_by_placeholder(re.compile(field_intent, re.IGNORECASE)).first,
            lambda: self.page.get_by_role("textbox", name=re.compile(field_intent, re.IGNORECASE)).first,
            lambda: self.page.get_by_role("searchbox").first,
            lambda: self.page.locator('input:visible, textarea:visible').first,
        ]
        for get_el in strategies:
            try:
                el = get_el()
                if await el.is_visible(timeout=800):
                    await el.click(timeout=2000)
                    await el.fill(text)
                    return True
            except Exception:
                continue
        return False
