"""CAPTCHA Solver — multi-strategy CAPTCHA bypass."""

import asyncio
import base64
import io
import logging
import os
import random
import tempfile
from pathlib import Path

from loguru import logger

try:
    import google.generativeai as genai
except ImportError:
    genai = None  # type: ignore

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


class CAPTCHASolver:
    """
    Multi-strategy CAPTCHA solver.
    Primary: Audio challenge bypass (free, no 3rd party)
    Fallback: 2captcha API or Gemini Vision for image CAPTCHAs.
    """

    def __init__(self, page, api_key: str, two_captcha_key: str = None):
        self.page = page
        self.api_key = api_key
        self.two_captcha_key = two_captcha_key or os.getenv("TWO_CAPTCHA_KEY")

        if genai:
            genai.configure(api_key=api_key)
            self.vision_model = genai.GenerativeModel("gemini-2.0-flash")
        else:
            self.vision_model = None

    async def solve(self, state) -> bool:
        """Detect CAPTCHA type and apply appropriate strategy."""

        # ── reCAPTCHA v2 ─────────────────────────────────────────────────
        if await self._is_recaptcha_v2():
            logger.info("[CAPTCHASolver] reCAPTCHA v2 detected — trying audio bypass")
            success = await self._solve_recaptcha_v2_audio()
            if success:
                return True
            if self.two_captcha_key:
                logger.info("[CAPTCHASolver] Audio failed — trying 2captcha API")
                return await self._solve_via_2captcha()
            return False

        # ── reCAPTCHA v3 (invisible) ─────────────────────────────────────
        if await self._is_recaptcha_v3():
            logger.info("[CAPTCHASolver] reCAPTCHA v3 — relying on human behaviour score")
            await asyncio.sleep(2.0)
            return True

        # ── hCaptcha ─────────────────────────────────────────────────────
        if await self._is_hcaptcha():
            logger.info("[CAPTCHASolver] hCaptcha detected")
            return await self._solve_hcaptcha_audio()

        # ── Cloudflare Turnstile ─────────────────────────────────────────
        if await self._is_turnstile():
            logger.info("[CAPTCHASolver] Cloudflare Turnstile — waiting for auto-resolve")
            try:
                await self.page.wait_for_selector(
                    "#cf-challenge-running", state="detached", timeout=15000
                )
                return True
            except Exception:
                return False

        # ── Image/Text CAPTCHA ───────────────────────────────────────────
        text_answer = await self._solve_image_captcha()
        if text_answer:
            return await self._submit_text_captcha(text_answer)

        return False

    # ── Detection Methods ────────────────────────────────────────────────────

    async def _is_recaptcha_v2(self) -> bool:
        return bool(
            await self.page.query_selector('iframe[src*="recaptcha/api2/anchor"]')
        )

    async def _is_recaptcha_v3(self) -> bool:
        return bool(
            await self.page.query_selector('script[src*="recaptcha/api.js?render="]')
        )

    async def _is_hcaptcha(self) -> bool:
        return bool(await self.page.query_selector('iframe[src*="hcaptcha.com"]'))

    async def _is_turnstile(self) -> bool:
        return bool(
            await self.page.query_selector(
                "#cf-challenge-running, .cf-browser-verification"
            )
        )

    # ── reCAPTCHA v2 Audio Bypass ────────────────────────────────────────────

    async def _solve_recaptcha_v2_audio(self) -> bool:
        """
        reCAPTCHA v2 audio challenge bypass:
        1. Click reCAPTCHA checkbox  2. Switch to audio
        3. Download audio  4. Transcribe with Gemini  5. Submit
        """
        try:
            recaptcha_frame = self.page.frame_locator('iframe[title="reCAPTCHA"]')
            await recaptcha_frame.locator("#recaptcha-anchor").click()
            await asyncio.sleep(random.uniform(1.5, 2.5))

            challenge_frame = self.page.frame_locator(
                'iframe[title="recaptcha challenge expires in two minutes"]'
            )

            audio_btn = challenge_frame.locator("#recaptcha-audio-button")
            if await audio_btn.count() == 0:
                return False

            await audio_btn.click()
            await asyncio.sleep(random.uniform(1.0, 2.0))

            audio_link = challenge_frame.locator(".rc-audiochallenge-tdownload-link")
            audio_src = await audio_link.get_attribute("href")
            if not audio_src:
                return False

            if httpx is None:
                logger.error("[CAPTCHASolver] httpx not installed")
                return False

            async with httpx.AsyncClient() as client:
                audio_response = await client.get(audio_src)
                audio_bytes = audio_response.content

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_bytes)
                audio_path = f.name

            answer = await self._transcribe_audio(audio_path)
            os.unlink(audio_path)

            if not answer:
                return False

            response_input = challenge_frame.locator("#audio-response")
            await response_input.fill(answer.strip().lower())
            await asyncio.sleep(random.uniform(0.3, 0.8))

            verify_btn = challenge_frame.locator("#recaptcha-verify-button")
            await verify_btn.click()
            await asyncio.sleep(2.0)

            success = await self.page.evaluate(
                "() => document.querySelector('.recaptcha-checkbox-checked') !== null"
            )
            return bool(success)

        except Exception as e:
            logger.error(f"[CAPTCHASolver] reCAPTCHA audio bypass failed: {e}")
            return False

    async def _transcribe_audio(self, audio_path: str):
        """Transcribe CAPTCHA audio using Gemini."""
        if not genai or not self.vision_model:
            return None
        try:
            audio_file = genai.upload_file(path=audio_path, mime_type="audio/mp3")
            response = self.vision_model.generate_content(
                [
                    "This is a reCAPTCHA audio challenge. Listen carefully and "
                    "transcribe ONLY the spoken words or numbers, nothing else.",
                    audio_file,
                ]
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"[CAPTCHASolver] Audio transcription failed: {e}")
            return None

    # ── hCaptcha ─────────────────────────────────────────────────────────────

    async def _solve_hcaptcha_audio(self) -> bool:
        """hCaptcha audio challenge attempt."""
        try:
            hcaptcha_frame = self.page.frame_locator(
                'iframe[src*="hcaptcha.com/checkbox"]'
            )
            await hcaptcha_frame.locator("#checkbox").click()
            await asyncio.sleep(2.0)

            challenge_frame = self.page.frame_locator(
                'iframe[src*="hcaptcha.com/challenge"]'
            )
            audio_btn = challenge_frame.locator('[aria-label="Get an audio challenge"]')
            if await audio_btn.count() > 0:
                await audio_btn.click()
                await asyncio.sleep(1.5)

            return False  # Extend as needed
        except Exception as e:
            logger.error(f"[CAPTCHASolver] hCaptcha failed: {e}")
            return False

    # ── 2captcha API Fallback ────────────────────────────────────────────────

    async def _solve_via_2captcha(self) -> bool:
        """Fall back to 2captcha API for difficult CAPTCHAs."""
        if httpx is None:
            return False
        try:
            site_key = await self.page.evaluate(
                "() => document.querySelector('[data-sitekey]')?.getAttribute('data-sitekey')"
            )
            if not site_key:
                return False

            async with httpx.AsyncClient(timeout=120) as client:
                submit = await client.post(
                    "http://2captcha.com/in.php",
                    data={
                        "key": self.two_captcha_key,
                        "method": "userrecaptcha",
                        "googlekey": site_key,
                        "pageurl": self.page.url,
                        "json": 1,
                    },
                )
                captcha_id = submit.json().get("request")
                if not captcha_id:
                    return False

                for _ in range(24):
                    await asyncio.sleep(5)
                    result = await client.get(
                        "http://2captcha.com/res.php",
                        params={
                            "key": self.two_captcha_key,
                            "action": "get",
                            "id": captcha_id,
                            "json": 1,
                        },
                    )
                    data = result.json()
                    if data.get("status") == 1:
                        token = data["request"]
                        await self.page.evaluate(
                            f"document.getElementById('g-recaptcha-response').innerHTML = '{token}';"
                        )
                        return True

            return False
        except Exception as e:
            logger.error(f"[CAPTCHASolver] 2captcha failed: {e}")
            return False

    # ── Image CAPTCHA (Gemini Vision) ────────────────────────────────────────

    async def _solve_image_captcha(self):
        """Use Gemini Vision to read a text/math CAPTCHA from screenshot."""
        if not self.vision_model:
            return None
        try:
            screenshot = await self.page.screenshot()
            from PIL import Image

            img = Image.open(io.BytesIO(screenshot))

            response = self.vision_model.generate_content(
                [
                    "This page has a CAPTCHA. Find the CAPTCHA challenge text "
                    "or math problem and solve it. Return ONLY the answer, "
                    "nothing else. If there is no CAPTCHA visible, return 'NONE'.",
                    img,
                ]
            )
            answer = response.text.strip()
            return None if answer == "NONE" else answer
        except Exception as e:
            logger.error(f"[CAPTCHASolver] Image CAPTCHA failed: {e}")
            return None

    async def _submit_text_captcha(self, answer: str) -> bool:
        """Type CAPTCHA answer into the response field and submit."""
        captcha_inputs = await self.page.query_selector_all(
            'input[name*="captcha"], input[id*="captcha"], input[placeholder*="captcha" i]'
        )
        if not captcha_inputs:
            return False

        await captcha_inputs[0].fill(answer)
        await asyncio.sleep(0.5)

        submit = await self.page.query_selector(
            'button[type="submit"], input[type="submit"]'
        )
        if submit:
            await submit.click()
            await asyncio.sleep(1.5)
            return True

        return False
