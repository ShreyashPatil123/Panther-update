"""Form Engine — AI-powered form filling via LLM reasoning."""

import asyncio
import json
import random
from typing import Dict

from loguru import logger

try:
    import google.generativeai as genai
except ImportError:
    genai = None  # type: ignore


class FormEngine:
    """
    AI-powered form filling engine. Maps available user data to form fields
    using LLM reasoning. Handles all form types including Google Forms.
    """

    def __init__(self, page, extension_client, api_key: str):
        self.page = page
        self.ext = extension_client

        if genai:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.0-flash")
        else:
            self.model = None

    async def fill(self, data: dict) -> bool:
        """
        Fill the current page's form(s) with provided data.
        data: dict mapping field descriptions to values
              e.g. {"name": "John Doe", "email": "john@example.com"}
        Returns True if form was successfully filled.
        """
        form_info = await self.ext.rpc("get_form_fields")
        if not form_info:
            return False

        fields = form_info.get("fields", [])
        g_form_fields = form_info.get("gFormFields")

        if g_form_fields:
            return await self._fill_google_form(g_form_fields, data)

        if not fields:
            return False

        return await self._fill_standard_form(fields, data)

    async def _fill_standard_form(self, fields: list, data: dict) -> bool:
        """Fill a standard HTML form."""
        mapping = await self._map_data_to_fields(fields, data)
        if not mapping:
            return False

        filled_count = 0
        for field_index, value in mapping.items():
            field = next(
                (f for f in fields if str(f["index"]) == str(field_index)), None
            )
            if not field or not value:
                continue

            try:
                rect = field["rect"]
                target_x = rect["x"] + rect["w"] / 2
                target_y = rect["y"] + rect["h"] / 2

                field_type = field["type"]

                if field_type in (
                    "text", "email", "password", "tel", "number", "search", "url"
                ):
                    await self.page.mouse.click(target_x, target_y)
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    await self.page.keyboard.press("Control+a")
                    await self.page.keyboard.type(
                        str(value), delay=random.uniform(60, 130)
                    )

                elif field_type == "select":
                    await self.page.select_option(
                        f'select[name="{field["name"]}"], select[id="{field["name"]}"]',
                        label=str(value),
                    )

                elif field_type in ("checkbox", "radio"):
                    if value and str(value).lower() not in ("false", "no", "0"):
                        await self.page.mouse.click(target_x, target_y)

                elif field_type == "textarea":
                    await self.page.mouse.click(target_x, target_y)
                    await asyncio.sleep(0.2)
                    await self.page.keyboard.press("Control+a")
                    await self.page.keyboard.type(
                        str(value), delay=random.uniform(40, 90)
                    )

                elif field_type == "date":
                    await self.page.mouse.click(target_x, target_y)
                    await asyncio.sleep(0.2)
                    await self.page.keyboard.type(str(value))

                filled_count += 1
                await asyncio.sleep(random.uniform(0.2, 0.5))

            except Exception as e:
                logger.warning(f"[FormEngine] Failed to fill field {field_index}: {e}")

        return filled_count > 0

    async def _fill_google_form(self, g_fields: list, data: dict) -> bool:
        """Specialized Google Forms handler."""
        mapping = await self._map_google_form(g_fields, data)

        filled = 0
        for item in mapping:
            question = item.get("question")
            answer = item.get("answer")
            q_type = item.get("type")

            if not answer:
                continue

            try:
                if q_type == "text":
                    input_el = await self.page.query_selector(
                        f'[aria-label="{question}"], input[type="text"]'
                    )
                    if input_el:
                        await input_el.click()
                        await asyncio.sleep(0.2)
                        await input_el.type(
                            str(answer), delay=random.uniform(60, 120)
                        )

                elif q_type == "paragraph":
                    textarea = await self.page.query_selector("textarea")
                    if textarea:
                        await textarea.click()
                        await textarea.type(str(answer), delay=50)

                elif q_type in ("radio", "checkbox"):
                    options = await self.page.query_selector_all(
                        '[role="radio"], [role="checkbox"]'
                    )
                    for opt in options:
                        opt_text = await opt.inner_text()
                        if str(answer).lower() in opt_text.lower():
                            await opt.click()
                            break

                elif q_type == "dropdown":
                    dropdown = await self.page.query_selector('[role="listbox"]')
                    if dropdown:
                        await dropdown.click()
                        await asyncio.sleep(0.5)
                        option = await self.page.query_selector(
                            f'[role="option"]:has-text("{answer}")'
                        )
                        if option:
                            await option.click()

                filled += 1
                await asyncio.sleep(random.uniform(0.3, 0.8))

            except Exception as e:
                logger.warning(f"[FormEngine] Google Form fill error: {e}")

        return filled > 0

    # ── LLM-based Data Mapping ──────────────────────────────────────────────

    async def _map_data_to_fields(self, fields: list, data: dict) -> dict:
        """Use LLM to map available data to form fields."""
        if not self.model:
            return {}

        prompt = f"""Map available data to form fields.

AVAILABLE DATA:
{json.dumps(data, indent=2)}

FORM FIELDS:
{json.dumps([{k: v for k, v in f.items() if k != 'rect'} for f in fields], indent=2)}

For each form field, determine the best value from available data.
Return a JSON object mapping field index (string) to value.
If no data matches a field, map to null.
Only return the JSON, nothing else."""

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.model.generate_content(prompt)
            )
            raw = response.text.strip()
            if "```" in raw:
                raw = raw.split("```")[1].split("```")[0].replace("json", "").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"[FormEngine] Data mapping failed: {e}")
            return {}

    async def _map_google_form(self, questions: list, data: dict) -> list:
        """Map data to Google Form questions."""
        if not self.model:
            return []

        prompt = f"""Fill in answers for these Google Form questions.

USER DATA:
{json.dumps(data, indent=2)}

QUESTIONS:
{json.dumps(questions, indent=2)}

Return a JSON array with objects: [{{"question": "...", "type": "...", "answer": "..."}}]
For questions you can answer from user data, provide an answer.
For questions you cannot answer, set answer to null."""

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.model.generate_content(prompt)
            )
            raw = response.text.strip()
            if "```" in raw:
                raw = raw.split("```")[1].split("```")[0].replace("json", "").strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"[FormEngine] Google Form mapping failed: {e}")
            return []
