"""DOM Intelligence — semantic element resolution via LLM reasoning."""

import asyncio
import json
from typing import Optional, Dict, Any

from loguru import logger

try:
    import google.generativeai as genai
except ImportError:
    genai = None  # type: ignore


class DOMIntelligence:
    """
    Semantic element resolution — finds elements by natural language intent
    instead of CSS selectors.  Uses Gemini Flash to reason about element purpose.
    """

    def __init__(self, page, extension_client):
        self.page = page
        self.ext = extension_client
        self._cache: Dict[str, str] = {}  # intent → resolved selector (per page load)
        self._current_url: str = ""

    def _clear_cache_if_navigated(self):
        if self.page.url != self._current_url:
            self._cache.clear()
            self._current_url = self.page.url

    async def resolve_element(self, intent: str) -> Optional[str]:
        """
        Resolve a natural language intent to a CSS selector.
        Returns None if no element found.

        Examples:
          "the search button"           → "button[type='submit']"
          "the email input field"       → "input[name='email']"
          "the accept cookies button"   → "#accept-all-cookies"
        """
        self._clear_cache_if_navigated()

        if intent in self._cache:
            return self._cache[intent]

        # Get candidate elements from extension client (or Playwright fallback)
        candidates = await self.ext.rpc("find_element", {"intent": intent})

        if not candidates or (isinstance(candidates, dict) and "error" in candidates):
            # Fallback: basic text-match selector
            return await self._fallback_text_match(intent)

        # Ask LLM to identify the best match
        selector = await self._llm_select_element(intent, candidates)

        if selector:
            self._cache[intent] = selector

        return selector

    async def _llm_select_element(
        self, intent: str, candidates: list
    ) -> Optional[str]:
        """Use Gemini Flash to select the best matching element."""
        if genai is None:
            logger.warning("[DOMIntelligence] google-generativeai not installed")
            return None

        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = f"""You are selecting the correct DOM element for an automation task.

INTENT: "{intent}"

CANDIDATE ELEMENTS (JSON):
{json.dumps(candidates[:15], indent=2)}

TASK: Which candidate best matches the intent? Return ONLY a JSON object:
{{
  "index": <0-based index of best match>,
  "css_selector": "<specific CSS selector to target this element>",
  "confidence": <0.0-1.0>
}}

Build the css_selector using id (preferred), name, aria-label, or structural position.
If no element matches with confidence > 0.5, return {{"index": -1, "css_selector": null, "confidence": 0}}.
"""

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: model.generate_content(prompt)
            )
            raw = response.text.strip()
            if "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            result = json.loads(raw)

            if result.get("confidence", 0) < 0.5 or result.get("index", -1) == -1:
                return None

            return result.get("css_selector")

        except Exception as e:
            logger.warning(f"[DOMIntelligence] LLM selection failed: {e}")
            return None

    async def _fallback_text_match(self, intent: str) -> Optional[str]:
        """Try to match by visible text as a fallback."""
        words = intent.lower().split()
        key_words = [
            w
            for w in words
            if w
            not in (
                "the", "a", "an", "this", "that",
                "button", "link", "field", "input",
            )
        ]

        for word in key_words[:3]:
            try:
                selector = f"text='{word}'"
                element = await self.page.query_selector(selector)
                if element:
                    return selector
            except Exception:
                continue

        return None

    async def extract_structured_data(self, schema: dict) -> dict:
        """
        Extract structured data from the current page based on a schema.
        Example schema: {"title": "article headline", "date": "publication date"}
        """
        if genai is None:
            return {}

        dom_snapshot = await self.ext.rpc(
            "capture_dom", {"options": {"maxLength": 30000}}
        )
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = f"""Extract structured data from this webpage DOM.

SCHEMA (what to extract):
{json.dumps(schema, indent=2)}

PAGE DOM:
{dom_snapshot}

Return ONLY a JSON object matching the schema keys with extracted values.
If a field is not found, use null."""

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: model.generate_content(prompt)
            )
            raw = response.text.strip()
            if "```" in raw:
                raw = raw.split("```")[1].split("```")[0].replace("json", "").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"[DOMIntelligence] Data extraction failed: {e}")
            return {}
