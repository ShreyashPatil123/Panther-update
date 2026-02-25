"""Extension Client — RPC stub with Playwright fallback for Phase 1."""

import asyncio
import json
from typing import Any, Dict, Optional

from loguru import logger


class ExtensionRPCClient:
    """
    RPC client for the PANTHER Chrome Extension DOM bridge.

    In Phase 1 (no Chrome extension), all calls fall back to direct
    Playwright page.evaluate() calls that replicate the extension's
    DOM capture, element finding, and form extraction logic.
    """

    def __init__(self, page):
        self.page = page
        self._extension_available = False

    async def rpc(self, method: str, params: Optional[Dict] = None) -> Any:
        """
        Call an RPC method. Falls back to Playwright evaluation
        when the Chrome extension is not running.
        """
        params = params or {}

        try:
            if method == "get_page_state":
                return await self._get_page_state()
            elif method == "capture_dom":
                return await self._capture_dom(params.get("options", {}))
            elif method == "find_element":
                return await self._find_element(
                    params.get("intent", ""), params.get("context", "")
                )
            elif method == "get_form_fields":
                return await self._get_form_fields()
            elif method == "capture_accessibility":
                return await self._capture_accessibility()
            elif method == "scroll_to_element":
                return await self._scroll_to_element(params.get("selector", ""))
            elif method == "highlight_element":
                return {"found": False, "note": "Extension not loaded"}
            elif method == "clear_highlights":
                return None
            else:
                logger.warning(f"[ExtensionRPC] Unknown method: {method}")
                return {"error": f"Unknown method: {method}"}
        except Exception as e:
            logger.error(f"[ExtensionRPC] {method} failed: {e}")
            return {"error": str(e)}

    # ── Playwright Fallback Implementations ────────────────────────────────

    async def _get_page_state(self) -> Dict:
        """Get current page state via Playwright."""
        return await self.page.evaluate("""() => ({
            url: window.location.href,
            title: document.title,
            readyState: document.readyState,
            scrollY: window.scrollY,
            scrollHeight: document.body.scrollHeight,
            viewportHeight: window.innerHeight,
            viewportWidth: window.innerWidth,
            hasCaptcha: !!(
                document.querySelector('iframe[src*="recaptcha"]') ||
                document.querySelector('iframe[src*="hcaptcha"]') ||
                document.querySelector('#cf-challenge-running') ||
                document.querySelector('[id*="captcha"]')
            ),
            hasForm: document.querySelectorAll('form').length > 0,
            dialogs: document.querySelectorAll('[role="dialog"], [role="alertdialog"]').length,
        })""")

    async def _capture_dom(self, options: Dict) -> str:
        """Capture cleaned DOM tree via Playwright."""
        max_length = options.get("maxLength", 50000)
        return await self.page.evaluate(f"""() => {{
            function cleanNode(node, depth) {{
                if (depth > 15) return null;
                if (node.nodeType === Node.TEXT_NODE) {{
                    const text = node.textContent.trim();
                    return text ? {{ type: "text", value: text }} : null;
                }}
                if (node.nodeType !== Node.ELEMENT_NODE) return null;

                const el = node;
                const style = window.getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") return null;

                const attrs = {{}};
                for (const attr of el.attributes) {{
                    if (["id", "class", "type", "name", "placeholder", "aria-label",
                         "aria-labelledby", "role", "href", "value", "data-testid"].includes(attr.name)) {{
                        attrs[attr.name] = attr.value;
                    }}
                }}

                const rect = el.getBoundingClientRect();
                const children = Array.from(el.childNodes)
                    .map(child => cleanNode(child, depth + 1))
                    .filter(Boolean);

                return {{
                    tag: el.tagName.toLowerCase(),
                    attrs,
                    text: el.innerText?.slice(0, 200) ?? "",
                    rect: {{ x: Math.round(rect.x), y: Math.round(rect.y),
                             w: Math.round(rect.width), h: Math.round(rect.height) }},
                    children: children.length > 0 ? children : undefined,
                }};
            }}

            const tree = cleanNode(document.body, 0);
            const json = JSON.stringify(tree);
            return json.slice(0, {max_length});
        }}""")

    async def _find_element(self, intent: str, context: str) -> list:
        """Find interactive elements matching an intent."""
        # Get the first word of the intent for basic scoring
        first_word = intent.lower().split()[0] if intent else ""
        return await self.page.evaluate(f"""(firstWord) => {{
            const candidates = [];
            document.querySelectorAll(
                'a, button, input, select, textarea, [onclick], [role="button"], [role="link"], [role="tab"], [role="menuitem"]'
            ).forEach(el => {{
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                const text = (el.innerText ?? el.value ?? el.placeholder ?? el.getAttribute("aria-label") ?? "").trim().toLowerCase();
                const score = text.includes(firstWord) ? 10 : 0;

                candidates.push({{
                    tag: el.tagName.toLowerCase(),
                    text: text.slice(0, 100),
                    id: el.id,
                    classes: el.className,
                    ariaLabel: el.getAttribute("aria-label") ?? "",
                    rect: {{ x: Math.round(rect.x), y: Math.round(rect.y),
                             w: Math.round(rect.width), h: Math.round(rect.height) }},
                    score,
                }});
            }});

            return candidates.sort((a, b) => b.score - a.score).slice(0, 20);
        }}""", first_word)

    async def _get_form_fields(self) -> Dict:
        """Extract form fields from the page."""
        return await self.page.evaluate("""() => {
            const fields = [];
            const formElements = document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), ' +
                'select, textarea, [role="combobox"], [role="listbox"]'
            );

            formElements.forEach((el, idx) => {
                let label = "";
                if (el.id) {
                    const labelEl = document.querySelector(`label[for="${el.id}"]`);
                    if (labelEl) label = labelEl.textContent.trim();
                }
                if (!label) label = el.getAttribute("aria-label") ?? el.placeholder ?? "";
                if (!label) {
                    const parent = el.closest("label");
                    if (parent) label = parent.textContent.replace(el.value, "").trim();
                }

                const rect = el.getBoundingClientRect();
                fields.push({
                    index: idx,
                    tag: el.tagName.toLowerCase(),
                    type: el.type ?? el.getAttribute("role") ?? "text",
                    label: label.slice(0, 150),
                    placeholder: el.placeholder ?? "",
                    name: el.name ?? el.id ?? "",
                    required: el.required,
                    currentValue: el.value ?? "",
                    options: el.tagName === "SELECT"
                        ? Array.from(el.options).map(o => ({ value: o.value, text: o.text }))
                        : undefined,
                    rect: { x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height) },
                });
            });

            return { fields };
        }""")

    async def _capture_accessibility(self) -> Dict:
        """Capture interactive elements as a lightweight accessibility tree."""
        return await self.page.evaluate("""() => {
            const interactives = [];
            const selectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [role="menuitem"], [tabindex]';
            document.querySelectorAll(selectors).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                interactives.push({
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute("role") ?? el.tagName.toLowerCase(),
                    label: el.getAttribute("aria-label") ?? el.textContent?.trim().slice(0, 80) ?? el.placeholder ?? "",
                    type: el.type ?? "",
                    id: el.id ?? "",
                    name: el.name ?? "",
                    rect: { x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height) },
                    inViewport: rect.top >= 0 && rect.bottom <= window.innerHeight,
                });
            });
            return { interactives, title: document.title, url: window.location.href };
        }""")

    async def _scroll_to_element(self, selector: str) -> Dict:
        """Scroll an element into view."""
        return await self.page.evaluate(f"""(sel) => {{
            const el = document.querySelector(sel);
            if (!el) return {{ scrolled: false }};
            el.scrollIntoView({{ behavior: "smooth", block: "center" }});
            return {{ scrolled: true }};
        }}""", selector)
