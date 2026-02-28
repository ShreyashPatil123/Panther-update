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
from src.utils.brand_normalizer import normalize_brand

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
1. ALWAYS reference elements by their [index] number from the tree.
2. If your objective was to "search" for something, and search results are now visible, YOU MUST IMMEDIATELY return `done` with the result summary. Do NOT click on individual results unless explicitly asked to "open" one.
3. After each action, you will see the updated screenshot + tree.
4. If an element you need isn't in the tree, try scrolling or waiting.
5. Maximum 3 retries per action before trying alternative approach.
6. When task is complete (especially after a search query is submitted), ALWAYS use `{"action": "done", "params": {"result": "Summary of search results"}, "done": true}`.

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

    # 3. SITE_MAP instant lookup — check if any known platform name appears in the task
    task_lower = task.lower()
    for name, site_url in SITE_MAP.items():
        # Match the site name as a whole word to avoid false positives
        if re.search(r'\b' + re.escape(name) + r'\b', task_lower):
            logger.info(f"[URL-Extractor] SITE_MAP instant match: '{name}' -> {site_url}")
            return site_url

    # 4. Fallback to None — will be resolved via LLM chain if needed.
    return None


def _extract_brand_name(task: str) -> Optional[str]:
    """Extract the brand/website name from a navigation command."""
    # Remove common action words to isolate the brand name
    patterns = [
        r"(?:open|go\s+to|visit|navigate\s+to|launch|check|show\s+me)\s+(?:the\s+)?(?:official\s+)?(?:website\s+(?:of|for)\s+)?(.+?)(?:'s\s+website|'s\s+site|'s\s+page|\s+website|\s+site|\s+page|\s+app)?(?:\s+and\s+.+)?$",
        r"(?:open|go\s+to|visit|navigate\s+to|launch|check)\s+(.+?)$",
    ]
    for p in patterns:
        m = re.search(p, task, re.IGNORECASE)
        if m:
            brand = m.group(1).strip().rstrip('.')
            # Strip trailing possessive 's
            brand = re.sub(r"'s$", "", brand).strip()
            # Skip empty
            if not brand:
                continue
            # Allow up to 5 words for multi-word brands (e.g., "pimpri chinchwad university")
            if len(brand.split()) > 5:
                continue
            # Skip if it contains search-related words
            if re.search(r'\b(search|find|look\s+up|how|what|why|when)\b', brand, re.IGNORECASE):
                continue
                
            # If it's literally just "the", skip it
            if brand.lower() == "the":
                continue
                
            return brand
    return None


async def _try_domain_heuristic(brand: str) -> Optional[str]:
    """Try common domain patterns for a brand name via concurrent HTTP HEAD requests."""
    # Clean brand name — strip possessive, special chars
    clean = re.sub(r"'s$", "", brand.strip(), flags=re.IGNORECASE)
    slug = re.sub(r'[^a-zA-Z0-9]', '', clean.lower())
    slug_hyphen = re.sub(r'\s+', '-', clean.lower().strip())
    slug_hyphen = re.sub(r'[^a-zA-Z0-9-]', '', slug_hyphen)

    if not slug or len(slug) < 2:
        return None

    # Build candidate list
    candidates = [
        f"https://www.{slug}.com",
        f"https://{slug}.com",
    ]

    # Multi-word: hyphenated version
    if slug != slug_hyphen and '-' in slug_hyphen:
        candidates.extend([
            f"https://www.{slug_hyphen}.com",
            f"https://{slug_hyphen}.com",
        ])

    # Educational institutions
    is_edu = bool(re.search(r'\b(university|college|institute|school|academy)\b', brand, re.IGNORECASE))
    if is_edu:
        candidates.extend([
            f"https://www.{slug}.ac.in",
            f"https://{slug}.ac.in",
            f"https://www.{slug}.edu",
            f"https://{slug}.edu",
            f"https://www.{slug}.edu.in",
        ])
        if slug != slug_hyphen and '-' in slug_hyphen:
            candidates.extend([
                f"https://www.{slug_hyphen}.ac.in",
                f"https://{slug_hyphen}.edu",
            ])

    # Alternative TLDs
    candidates.extend([
        f"https://www.{slug}.in",
        f"https://www.{slug}.org",
        f"https://www.{slug}.io",
        f"https://{slug}.co",
        f"https://www.{slug}.ai",
        f"https://{slug}.app",
        f"https://{slug}.dev",
        f"https://www.{slug}.net",
    ])

    # ── Concurrent probing — try all at once, return first success ──
    async def _probe(session: aiohttp.ClientSession, url: str) -> Optional[str]:
        try:
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=3),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                if resp.status < 400:
                    logger.info(f"[URL-Heuristic] '{brand}' -> {url} (status={resp.status})")
                    return url
        except Exception:
            pass
        return None

    async with aiohttp.ClientSession() as session:
        tasks = [_probe(session, url) for url in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, str) and r:
                return r
    return None


def _sanitize_url(url: str) -> str:
    """Strip Google redirect wrappers and clean resolved URLs.
    
    Google often wraps URLs like: google.com/url?q=https://open.spotify.com/
    This extracts the actual destination URL.
    """
    if not url:
        return url
    import urllib.parse
    # Unwrap Google redirect: google.com/url?q=<actual_url>
    if "google.com/url" in url:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if "q" in params and params["q"][0].startswith("http"):
            unwrapped = params["q"][0]
            logger.info(f"[URL-Sanitize] Unwrapped Google redirect: {url} → {unwrapped}")
            return unwrapped
        if "url" in params and params["url"][0].startswith("http"):
            unwrapped = params["url"][0]
            logger.info(f"[URL-Sanitize] Unwrapped Google redirect: {url} → {unwrapped}")
            return unwrapped
    return url


async def _resolve_url_via_llm_chain(
    task: str, nvidia_key: Optional[str], google_model, pplx_key: Optional[str]
) -> Optional[str]:
    """
    Intelligently resolve the canonical domain from natural language.
    Robust fallback chain that works even without NVIDIA/Perplexity keys:
    1. Brand-to-domain heuristic (try {name}.com — zero API cost)  
    2. Gemini (reliable, usually has Google key)
    3. NVIDIA (if key available)
    4. Perplexity (if key available)  
    """

    # ── Tier 1: Brand-to-domain heuristic ──────────────────────────────
    brand = _extract_brand_name(task)
    if brand:
        logger.info(f"[URL-Resolver] Trying domain heuristic for brand: '{brand}'")
        heuristic_url = await _try_domain_heuristic(brand)
        if heuristic_url:
            logger.info(f"[URL-Resolver] Heuristic resolved: '{brand}' -> {heuristic_url}")
            return heuristic_url

    # ── Common LLM prompt ──────────────────────────────────────────────
    system_prompt = (
        "You are a URL resolver. Given a user command, return ONLY the official website URL. "
        "Respond with just the URL, nothing else. Example: https://www.zara.com"
    )
    user_prompt = f"What is the official website URL for this command: {task}"

    def _parse_url_from_response(content: str) -> Optional[str]:
        """Extract a valid URL from an LLM response, even if it's messy."""
        if not content:
            return None
        content = content.strip()
        # Try to find a URL in the response
        m = re.search(r'https?://[^\s,\'"<>\]\)]+', content)
        if m:
            url = m.group(0).rstrip('.')
            return url
        # Try bare domain pattern
        m = re.search(r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|org|net|io|co|ai|dev|app|me|in|edu|gov|tech|tv))\b', content)
        if m:
            return f"https://www.{m.group(1)}"
        return None

    # ── Tier 2: Perplexity API (Fastest and most accurate for URLs) ────
    if pplx_key and pplx_key not in ("your_perplexity_key_here", ""):
        try:
            api_url = "https://api.perplexity.ai/chat/completions"
            headers = {"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
            data = {
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 60,
                "temperature": 0.1
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        url = _parse_url_from_response(content)
                        if url:
                            logger.info(f"[URL-Resolver] Perplexity resolved: {url}")
                            return url
        except Exception as e:
            logger.warning(f"[URL-Resolver] Perplexity failed: {e}")

    # ── Tier 3: Google Gemini (reliable fallback) ──────────────────────
    if google_model:
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: google_model.generate_content(f"{system_prompt}\n\n{user_prompt}")
            )
            url = _parse_url_from_response(resp.text)
            if url:
                logger.info(f"[URL-Resolver] Gemini resolved: {url}")
                return url
        except Exception as e:
            logger.warning(f"[URL-Resolver] Google Gemini failed: {e}")

    # ── Tier 4: NVIDIA API ─────────────────────────────────────────────
    if nvidia_key and nvidia_key not in ("your_api_key_here", ""):
        try:
            api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {nvidia_key}", "Content-Type": "application/json"}
            data = {
                "model": "meta/llama-3.1-8b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 60,
                "temperature": 0.1
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        url = _parse_url_from_response(content)
                        if url:
                            logger.info(f"[URL-Resolver] NVIDIA resolved: {url}")
                            return url
        except Exception as e:
            logger.warning(f"[URL-Resolver] NVIDIA failed: {e}")

    # ── Tier 4: Perplexity API ─────────────────────────────────────────
    if pplx_key and pplx_key not in ("your_perplexity_key_here", ""):
        try:
            api_url = "https://api.perplexity.ai/chat/completions"
            headers = {"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"}
            data = {
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 60,
                "temperature": 0.1
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        url = _parse_url_from_response(content)
                        if url:
                            logger.info(f"[URL-Resolver] Perplexity resolved: {url}")
                            return url
        except Exception as e:
            logger.warning(f"[URL-Resolver] Perplexity failed: {e}")

    # ── Tier 5: DuckDuckGo Instant Answer API (free, no key needed) ────
    # Returns OfficialWebsite/AbstractURL for known brands and orgs.
    brand = _extract_brand_name(task)
    if brand:
        try:
            import urllib.parse
            ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote_plus(brand)}&format=json&no_redirect=1&skip_disambig=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(ddg_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        # Priority: OfficialWebsite > AbstractURL > Redirect
                        official = data.get("OfficialWebsite") or data.get("AbstractURL") or data.get("Redirect")
                        if official and official.startswith("http"):
                            logger.info(f"[URL-Resolver] DuckDuckGo resolved: '{brand}' -> {official}")
                            return official
                        # Check related topics for a URL
                        for topic in data.get("RelatedTopics", []):
                            first_url = topic.get("FirstURL", "")
                            if first_url and not "duckduckgo.com" in first_url:
                                logger.info(f"[URL-Resolver] DuckDuckGo topic URL: '{brand}' -> {first_url}")
                                return first_url
        except Exception as e:
            logger.warning(f"[URL-Resolver] DuckDuckGo failed: {e}")

    # ── Tier 6: Google I'm Feeling Lucky redirect ──────────────────────
    # Follows redirects to land on the actual website, not the search page.
    if brand:
        try:
            import urllib.parse
            lucky_url = f"https://www.google.com/search?btnI&q={urllib.parse.quote_plus(brand + ' official website')}"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    lucky_url,
                    timeout=aiohttp.ClientTimeout(total=6),
                    allow_redirects=True,
                    ssl=False,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                ) as resp:
                    final_url = _sanitize_url(str(resp.url))
                    # Only use if it redirected away from Google entirely
                    if "google.com" not in final_url and final_url.startswith("http"):
                        logger.info(f"[URL-Resolver] Google Lucky resolved: '{brand}' -> {final_url}")
                        return final_url
        except Exception as e:
            logger.warning(f"[URL-Resolver] Google Lucky failed: {e}")

    # ── Absolute fallback: Google search (last resort) ─────────────────
    if brand:
        import urllib.parse
        google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(brand + ' official website')}"
        logger.info(f"[URL-Resolver] Absolute fallback: Google search: {google_url}")
        return google_url
    else:
        # If all else fails, and it isn't a brand, just search the task
        import urllib.parse
        google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(task)}"
        logger.info(f"[URL-Resolver] Absolute fallback (no brand): Google search: {google_url}")
        return google_url

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
            # Strip trailing platform references and filler phrases
            q = re.sub(r'\s+(?:on|in|at)\s+\S+.*$', '', q, flags=re.IGNORECASE)
            q = re.sub(r'\s+and\s+(?:open|play|watch|show|view)\s+it\s*$', '', q, flags=re.IGNORECASE)
            
            # Reduce verbose sentences to just the key targets if possible
            # e.g., "for shoes and sort by price" -> "shoes" (basic heuristic)
            q = re.sub(r'\s+(?:and|to|with).+$', '', q, flags=re.IGNORECASE)
            
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
        
        # If no explicit URL is found but the user wants to go to an official website or we have a query, run the LLM fallback chain
        if not url and (re.search(r'\b(website|site|page|open|go\s+to|visit)\b', task.lower()) or " on " in task.lower()):
            # ── Normalize the brand name (fix typos/spacing) ──────────
            raw_brand = _extract_brand_name(task)
            if raw_brand:
                normalized = await normalize_brand(raw_brand, self.model)
                if normalized and normalized != raw_brand.lower():
                    yield {"type": "action", "message": f"✏️ Normalized: '{raw_brand}' → '{normalized}'"}
                    # Re-check SITE_MAP with normalized name
                    if normalized in SITE_MAP:
                        url = SITE_MAP[normalized]
                        yield {"type": "action", "message": f"✨ Matched known site: {url}"}
                    else:
                        # Build a normalized task for the resolution chain
                        task_for_resolve = re.sub(re.escape(raw_brand), normalized, task, flags=re.IGNORECASE)
                else:
                    task_for_resolve = task
            else:
                task_for_resolve = task

            if not url:
                yield {"type": "action", "message": f"🌐 Resolving official website..."}
                nvidia_key = os.getenv("NVIDIA_API_KEY")
                pplx_key = os.getenv("PERPLEXITY_API_KEY")
                
                resolved_url = await _resolve_url_via_llm_chain(
                    task=task_for_resolve,
                    nvidia_key=nvidia_key,
                    google_model=self.model,
                    pplx_key=pplx_key
                )
                
                if resolved_url:
                    url = resolved_url
                    yield {"type": "action", "message": f"✨ Resolved to: {url}"}

        if url:
            url = _sanitize_url(url)  # Strip Google redirect wrappers
            yield {"type": "action", "message": f"🔗 Navigating to {url}"}
            try:
                await self._navigate(url)
                yield {"type": "action", "message": f"✅ Loaded: {self.page.url}"}
            except Exception as e:
                yield {"type": "error", "message": f"Navigation failed: {e}"}
                return

        # ── Search within the loaded page (if query was extracted) ─────────
        if query:
            yield {"type": "action", "message": f"🔍 Searching: {query}"}
            searched = await self._universal_search(query)
            if searched:
                await asyncio.sleep(2.0)
                yield {"type": "action", "message": "✅ Search submitted"}

        # ── Google fallback: if still on about:blank, search Google ──────
        current = self.page.url
        if not current or current in ("about:blank", ""):
            # Use clean brand name for a better search query
            brand = _extract_brand_name(task)
            google_query = brand + " official website" if brand else (query or task)
            yield {"type": "action", "message": f"🔍 Searching Google: {google_query}"}
            try:
                import urllib.parse
                google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(google_query)}"
                await self._navigate(google_url)
                yield {"type": "action", "message": f"✅ Google search loaded"}
            except Exception as e:
                yield {"type": "error", "message": f"Google fallback failed: {e}"}
                return

        # ── Early exit for navigation/search-only tasks ──────────────────────
        # If we successfully submitted a search query via _universal_search on a known URL, 
        # or if it was a pure navigation command, we can return the page state 
        # immediately instead of entering the Gemini loop, which often hallucinates 
        # actions after finding the target.
        if (url and not query) or (url and query and searched) or (url and not searched):
            logger.info(f"[SubAgent] Task satisfied via pre-navigation/search. URL={self.page.url}")
            try:
                text = await self._extract_text()
            except Exception:
                text = ""
            yield {
                "type": "result",
                "message": "✅ Navigation complete",
                "data": {
                    "result": text[:3000] if text else f"Opened {self.page.url}",
                    "final_url": self.page.url,
                    "steps_taken": 1,
                },
            }
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
        """Find and use search input on ANY website with typing animation."""
        import time
        import ctypes

        # ── Phase 1: Wait for the page to be interactive ──────────────────
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        # Extra grace period for JS-heavy sites (YouTube, Amazon, etc.)
        await asyncio.sleep(2.0)

        # ── Phase 2: Find the search input ────────────────────────────────
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

        target_el = None
        for get_el in strategies:
            try:
                el = get_el()
                if await el.is_visible(timeout=1500):
                    target_el = el
                    break
            except Exception:
                continue

        if not target_el:
            logger.warning("[SubAgent] No search input found on page")
            return False

        # ── Phase 3: Click the search input to focus it ───────────────────
        try:
            await target_el.click(timeout=3000)
            await asyncio.sleep(0.5)
            # Clear any existing content
            await target_el.fill("")
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"[SubAgent] Could not click search input: {e}")
            return False

        # ── Phase 4: Type the query character-by-character via ctypes ─────
        def _type_search_query(text: str):
            """Simulate human-like typing using Windows ctypes keyboard events."""
            KEYEVENTF_KEYUP = 0x0002
            VK_RETURN = 0x0D

            for char in text:
                vk = ctypes.windll.user32.VkKeyScanW(ord(char))
                shift = (vk & 0x0100) != 0
                vk_code = vk & 0xFF

                if shift:
                    ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)  # Shift down
                ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
                time.sleep(0.02)
                ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
                if shift:
                    ctypes.windll.user32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.04)  # Slightly slower than URL typing for a natural feel

            # Press Enter
            time.sleep(0.15)
            ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)

        try:
            # Ensure the browser window is focused
            await self.page.bring_to_front()
            await asyncio.sleep(0.3)

            # Run the typing animation in a thread (ctypes is blocking)
            await asyncio.to_thread(_type_search_query, query)

            # Wait for search results to load
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                await asyncio.sleep(2.0)

            return True
        except Exception as e:
            logger.warning(f"[SubAgent] Typing animation failed, falling back to fill: {e}")
            # Fallback: use Playwright fill if ctypes fails
            try:
                await target_el.fill(query)
                await asyncio.sleep(0.3)
                await self.page.keyboard.press("Enter")
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    await asyncio.sleep(2.0)
                return True
            except Exception:
                return False

    # ── Core helpers ─────────────────────────────────────────────────────────

    async def _navigate(self, url: str):
        if not url.startswith("http"):
            url = "https://" + url

        logger.info(f"[SubAgent] Navigating to: {url}")

        try:
            # Use Playwright's reliable page.goto() for navigation
            await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            logger.warning(f"[SubAgent] page.goto failed: {e}, retrying with longer timeout")
            try:
                await self.page.goto(url, wait_until="commit", timeout=20000)
            except Exception as e2:
                logger.error(f"[SubAgent] Navigation failed completely: {e2}")
                raise

        # Wait for the page to fully settle
        try:
            await self.page.wait_for_load_state("load", timeout=8000)
        except Exception:
            pass  # Some pages never fully "load" (streaming, infinite scroll)

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

            # Robust JSON extraction
            json_match = re.search(r'\{(?:[^{}]|(?(r)\{.*\}))*\}', raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)
            elif "```json" in raw:
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
        # To better match Playwright's accessibility tree, we just click the physical center
        # of the element if we can't find it via strict accessibility locators.
        try:
            return await self.page.evaluate("""(idx) => {
                const els = document.querySelectorAll(
                    'a, button, input, textarea, select, [role="button"], [role="link"], [role="searchbox"], [tabindex]'
                );
                // Since tree order != DOM order, this is highly unreliable.
                // We'll just try to click it.
                const el = els[idx - 1];
                if (el) { 
                    el.scrollIntoView({behavior: 'smooth', block: 'center'}); 
                    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    return true; 
                }
                return false;
            }""", idx)
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
