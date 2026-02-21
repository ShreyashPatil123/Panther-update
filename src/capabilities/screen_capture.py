"""Screen capture service for vision models and Gemini Live.

Captures the user's screen periodically, ONLY when the app is in the background.
All processing is in-memory — screenshots are never saved to disk.
"""
import asyncio
import base64
import io
from typing import Callable, Dict, List, Optional

from loguru import logger


class ScreenCaptureService:
    """Manages periodic screen capture with background-only enforcement.

    Privacy guarantees:
        - capture_once() returns None if the app is in the foreground
        - No screenshot data is ever written to disk
        - Buffered frames are cleared when the app returns to foreground
        - Frame data is never logged
    """

    def __init__(self, monitor: int = 0, interval: float = 3.0):
        self._monitor = monitor
        self._interval = interval
        self._app_in_background = False
        self._running = False
        self._capture_task: Optional[asyncio.Task] = None
        self._latest_frame: Optional[bytes] = None  # JPEG bytes, in-memory only
        self._frame_callbacks: List[Callable[[bytes], None]] = []
        self._vision_enabled = False
        self._gemini_enabled = False
        self._mss_available = True
        self._last_ocr_text: Optional[str] = None
        self._ocr_callbacks: List[Callable[[str], None]] = []

        # Check mss availability at init
        try:
            import mss  # noqa: F401
        except ImportError:
            self._mss_available = False
            logger.warning("mss package not installed. Screen capture unavailable.")

    @property
    def is_available(self) -> bool:
        """Whether screen capture is available (mss installed)."""
        return self._mss_available

    @property
    def is_capturing(self) -> bool:
        """Whether capture is currently active."""
        return (
            self._running
            and self._app_in_background
            and (self._vision_enabled or self._gemini_enabled)
        )

    @property
    def is_app_in_background(self) -> bool:
        """Whether the app is currently in the background."""
        return self._app_in_background

    @property
    def vision_enabled(self) -> bool:
        return self._vision_enabled

    @vision_enabled.setter
    def vision_enabled(self, value: bool):
        self._vision_enabled = value

    @property
    def gemini_enabled(self) -> bool:
        return self._gemini_enabled

    @gemini_enabled.setter
    def gemini_enabled(self, value: bool):
        self._gemini_enabled = value

    @property
    def monitor(self) -> int:
        return self._monitor

    @monitor.setter
    def monitor(self, value: int):
        self._monitor = value

    @property
    def interval(self) -> float:
        return self._interval

    @interval.setter
    def interval(self, value: float):
        self._interval = max(1.0, min(10.0, value))

    def available_monitors(self) -> List[Dict]:
        """Enumerate available monitors.

        Returns:
            List of dicts with index, width, height for each monitor.
        """
        if not self._mss_available:
            return [{"index": 0, "name": "Primary", "width": 0, "height": 0}]
        try:
            import mss

            with mss.mss() as sct:
                result = []
                # sct.monitors[0] = all screens combined, [1] = primary, [2+] = others
                for i, m in enumerate(sct.monitors[1:], start=0):
                    name = "Primary" if i == 0 else f"Monitor {i + 1}"
                    result.append(
                        {
                            "index": i,
                            "name": f"{name} ({m['width']}x{m['height']})",
                            "width": m["width"],
                            "height": m["height"],
                        }
                    )
                return result if result else [{"index": 0, "name": "Primary", "width": 0, "height": 0}]
        except Exception as e:
            logger.error(f"Failed to enumerate monitors: {e}")
            return [{"index": 0, "name": "Primary", "width": 0, "height": 0}]

    def capture_once(self, monitor_index: Optional[int] = None) -> Optional[bytes]:
        """Capture a single screenshot. Returns JPEG bytes or None.

        PRIVACY: Returns None if the app is in the foreground.
        """
        if not self._app_in_background:
            return None
        if not self._mss_available:
            return None

        try:
            import mss
            from PIL import Image

            idx = monitor_index if monitor_index is not None else self._monitor

            with mss.mss() as sct:
                monitors = sct.monitors
                # monitors[0] = all, [1] = primary, [2+] = secondary
                mon = monitors[min(idx + 1, len(monitors) - 1)]
                screenshot = sct.grab(mon)

                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                # Resize for API efficiency (max 1024px wide)
                if img.width > 1024:
                    ratio = 1024 / img.width
                    img = img.resize((1024, int(img.height * ratio)), Image.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                return buf.getvalue()
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return None

    def force_capture(self, monitor_index: Optional[int] = None) -> Optional[bytes]:
        """Capture a screenshot on demand regardless of foreground/background state.
        Returns JPEG bytes or None on failure.
        """
        if not self._mss_available:
            return None

        try:
            import mss
            from PIL import Image

            idx = monitor_index if monitor_index is not None else self._monitor

            with mss.mss() as sct:
                monitors = sct.monitors
                mon = monitors[min(idx + 1, len(monitors) - 1)]
                screenshot = sct.grab(mon)

                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                # Resize for API efficiency (max 1024px wide)
                if img.width > 1024:
                    ratio = 1024 / img.width
                    img = img.resize((1024, int(img.height * ratio)), Image.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                return buf.getvalue()
        except Exception as e:
            logger.error(f"Force screen capture failed: {e}")
            return None

    def get_latest_frame(self) -> Optional[bytes]:
        """Get the most recent captured frame (JPEG bytes)."""
        if not self._app_in_background:
            return None
        return self._latest_frame

    def get_latest_base64(self) -> Optional[str]:
        """Get the most recent frame as a base64-encoded JPEG string."""
        frame = self.get_latest_frame()
        if frame is None:
            return None
        return base64.b64encode(frame).decode("ascii")

    def set_app_in_background(self, is_background: bool):
        """Update app foreground/background state.

        When transitioning to foreground, immediately clears buffered frames.
        """
        was_background = self._app_in_background
        self._app_in_background = is_background

        if was_background and not is_background:
            # Returning to foreground — clear all buffered data immediately
            self._latest_frame = None
            self._last_ocr_text = None
            logger.debug("App returned to foreground — screen capture paused, frames cleared")
        elif not was_background and is_background:
            logger.debug("App moved to background — screen capture may activate")

    def on_frame_captured(self, callback: Callable[[bytes], None]):
        """Register a callback invoked each time a new frame is captured."""
        self._frame_callbacks.append(callback)

    def remove_frame_callback(self, callback: Callable[[bytes], None]):
        """Remove a previously registered frame callback."""
        try:
            self._frame_callbacks.remove(callback)
        except ValueError:
            pass

    def on_ocr_text(self, callback: Callable[[str], None]):
        """Register a callback invoked when new OCR text is extracted."""
        self._ocr_callbacks.append(callback)

    def remove_ocr_callback(self, callback: Callable[[str], None]):
        """Remove a previously registered OCR text callback."""
        try:
            self._ocr_callbacks.remove(callback)
        except ValueError:
            pass

    def get_latest_ocr_text(self) -> Optional[str]:
        """Get the most recent OCR-extracted text. Returns None if app in foreground."""
        if not self._app_in_background:
            return None
        return self._last_ocr_text

    def set_ocr_text(self, text: Optional[str]):
        """Store OCR result and fire callbacks if text has changed (dedup).

        Called by the OCR pipeline after extracting text from a captured frame.
        Only notifies callbacks when the screen content has meaningfully changed.
        """
        if text and text != self._last_ocr_text:
            self._last_ocr_text = text
            for cb in self._ocr_callbacks:
                try:
                    cb(text)
                except Exception:
                    pass

    def start(self):
        """Start the periodic capture loop."""
        if self._running:
            return
        if not self._mss_available:
            logger.warning("Cannot start screen capture — mss not installed")
            return
        self._running = True
        self._capture_task = asyncio.create_task(self._capture_loop())
        logger.info("Screen capture service started")

    def stop(self):
        """Stop the capture loop and clear all buffered data."""
        self._running = False
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
        self._capture_task = None
        self._latest_frame = None
        self._last_ocr_text = None
        self._frame_callbacks.clear()
        self._ocr_callbacks.clear()
        logger.info("Screen capture service stopped")

    async def _capture_loop(self):
        """Background loop: capture screen at configured interval."""
        try:
            while self._running:
                if self._app_in_background and (self._vision_enabled or self._gemini_enabled):
                    frame = await asyncio.to_thread(self.capture_once, self._monitor)
                    if frame is not None:
                        self._latest_frame = frame
                        for cb in self._frame_callbacks:
                            try:
                                cb(frame)
                            except Exception:
                                pass
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Screen capture loop error: {e}")
