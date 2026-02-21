"""Gemini Live push-to-talk speech service for Panther.

Self-contained QObject that manages a persistent Gemini Live session
with push-to-talk (ActivityStart / ActivityEnd) for speech boundaries.

Audio pipeline:
    Mic (16 kHz int16 PCM) → asyncio.Queue → session.send_realtime_input()
    session.receive() → ThreadSafeAudioBuffer → sounddevice OutputStream (24 kHz int16 PCM)

API key: read automatically from GOOGLE_API_KEY or GEMINI_API_KEY env var
via the official google-genai SDK.
"""

import asyncio
import logging
import threading
from typing import Optional

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("panther.gemini_live")

_DEFAULT_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"


# ---------------------------------------------------------------------------
# Thread-safe byte buffer for speaker playback
# ---------------------------------------------------------------------------

class _ThreadSafeAudioBuffer:
    """Lock-based byte buffer shared between the async receive loop
    (writer) and the sounddevice OutputStream callback (reader)."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._lock = threading.Lock()

    def write(self, data: bytes) -> None:
        with self._lock:
            self._buf.extend(data)

    def read(self, n: int) -> bytes:
        with self._lock:
            out = bytes(self._buf[:n])
            del self._buf[:n]
            return out

    def available(self) -> int:
        with self._lock:
            return len(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class GeminiLiveSpeechService(QObject):
    """Push-to-talk speech service using the Gemini Live API.

    Keeps ONE persistent Gemini Live session open.  Each user utterance
    is bracketed by ``ActivityStart`` / ``ActivityEnd`` messages so the
    server knows when speech starts and stops (automatic VAD is disabled).

    Signals
    -------
    status_changed(str)
        One of ``"idle"``, ``"connecting"``, ``"listening"``,
        ``"speaking"``, ``"error"``.
    partial_transcript(str)
        Intermediate transcription text (input or output).
    error_occurred(str)
        Human-readable error string.
    """

    status_changed = pyqtSignal(str)
    partial_transcript = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        system_prompt: str = "You are Panther, a helpful AI assistant.",
        api_key: str | None = None,
        mic_sample_rate: int = 16_000,
        speaker_sample_rate: int = 24_000,
        mic_block_size: int = 1024,
        model: str = _DEFAULT_MODEL,
        voice: str = "Puck",
        vad_enabled: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self._system_prompt = system_prompt
        self._api_key = api_key  # explicit key; if None, SDK reads from env
        self._mic_rate = mic_sample_rate
        self._spk_rate = speaker_sample_rate
        self._mic_block = mic_block_size
        self._model = model
        self._voice = voice

        # ── Gemini SDK objects (lazy-created in _run_session) ──
        self._client = None          # genai.Client
        self._session = None         # AsyncSession inside context manager

        # ── State ──
        self._state: str = "idle"
        self._running: bool = False
        self._recording: bool = False

        # ── Async tasks ──
        self._session_task: Optional[asyncio.Task] = None
        self._send_task: Optional[asyncio.Task] = None

        # ── Audio I/O ──
        self._mic_stream: Optional[sd.InputStream] = None
        self._spk_stream: Optional[sd.OutputStream] = None
        self._mic_queue: asyncio.Queue = asyncio.Queue()
        self._spk_buffer = _ThreadSafeAudioBuffer()

        # ── Voice Activity Detection ──
        from src.audio.vad import EnergyVAD, VADConfig

        self._vad = EnergyVAD(VADConfig(enabled=vad_enabled))

        # ── Reconnect state ──
        self._reconnect_attempt: int = 0
        self._max_reconnect_delay: float = 30.0

        # ── Event loop reference (captured on start) ──
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """True while the user is speaking or the model is responding."""
        return self._state in ("listening", "speaking")

    # ------------------------------------------------------------------
    # Public API  (all safe to call from the Qt main thread)
    # ------------------------------------------------------------------

    def start_conversation(self) -> None:
        """Open the persistent Gemini Live session.  Call once at app start."""
        self._loop = asyncio.get_event_loop()
        self._running = True
        self._session_task = asyncio.create_task(self._run_session())
        logger.info("start_conversation() scheduled")

    def start_turn(self) -> None:
        """Push-to-talk BEGIN — mic button pressed."""
        if self._session is None:
            self.error_occurred.emit("Voice session not ready yet. Please wait…")
            return
        if self._recording:
            return
        self._recording = True
        asyncio.create_task(self._begin_turn())

    def stop_turn(self) -> None:
        """Push-to-talk END — mic button released."""
        if not self._recording:
            return
        self._recording = False
        asyncio.create_task(self._end_turn())

    def shutdown(self) -> None:
        """Graceful teardown — call on app close."""
        self._running = False
        self._recording = False
        asyncio.create_task(self._cleanup())

    # ------------------------------------------------------------------
    # Internal: state helpers
    # ------------------------------------------------------------------

    def _set_status(self, status: str) -> None:
        if status != self._state:
            self._state = status
            logger.info("Status → %s", status)
            self.status_changed.emit(status)

    # ------------------------------------------------------------------
    # Internal: session lifecycle  (runs as a long-lived asyncio.Task)
    # ------------------------------------------------------------------

    async def _run_session(self) -> None:
        """Connect → receive loop → auto-reconnect on failure."""
        while self._running:
            try:
                self._set_status("connecting")

                # Lazy-create client
                if self._client is None:
                    from google import genai
                    if self._api_key:
                        self._client = genai.Client(api_key=self._api_key)
                        logger.info("genai.Client created (explicit API key)")
                    else:
                        self._client = genai.Client()
                        logger.info("genai.Client created (API key from env)")

                from google.genai import types

                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    system_instruction=types.Content(
                        parts=[types.Part(text=self._system_prompt)]
                    ),
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self._voice,
                            )
                        )
                    ),
                    realtime_input_config={
                        "automatic_activity_detection": {"disabled": True}
                    },
                    input_audio_transcription={},
                    output_audio_transcription={},
                )

                logger.info("Connecting to Gemini Live (%s)…", self._model)

                async with self._client.aio.live.connect(
                    model=self._model, config=config,
                ) as session:
                    self._session = session
                    self._reconnect_attempt = 0
                    self._start_speaker_stream()
                    self._set_status("idle")
                    logger.info("Gemini Live session active — ready for push-to-talk")

                    # Receive loop blocks here until session closes
                    await self._receive_loop(session)

            except asyncio.CancelledError:
                logger.info("Session task cancelled")
                break

            except Exception as exc:
                logger.error("Session error: %s", exc)
                self._session = None
                self._stop_mic()

                if not self._running:
                    break

                self._reconnect_attempt += 1
                delay = min(
                    2 ** self._reconnect_attempt, self._max_reconnect_delay
                )
                self._set_status("error")
                self.error_occurred.emit(
                    f"Connection lost. Reconnecting in {delay:.0f}s…"
                )
                logger.info(
                    "Reconnecting in %.1fs (attempt %d)",
                    delay,
                    self._reconnect_attempt,
                )
                await asyncio.sleep(delay)

        # Session loop exited
        self._stop_speaker_stream()
        self._set_status("idle")

    # ------------------------------------------------------------------
    # Internal: receive loop
    # ------------------------------------------------------------------

    async def _receive_loop(self, session) -> None:
        """Process incoming messages from Gemini Live until the
        session closes or ``_running`` is set to False."""
        speaking = False

        async for response in session.receive():
            if not self._running:
                break

            sc = response.server_content
            if sc is None:
                continue

            # Audio chunks from the model
            if sc.model_turn and sc.model_turn.parts:
                if not speaking:
                    speaking = True
                    if not self._recording:
                        self._set_status("speaking")
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        self._spk_buffer.write(part.inline_data.data)

            # Output transcription (model speech → text)
            if (
                hasattr(sc, "output_transcription")
                and sc.output_transcription
                and sc.output_transcription.text
            ):
                self.partial_transcript.emit(sc.output_transcription.text)

            # Input transcription  (user speech → text)
            if (
                hasattr(sc, "input_transcription")
                and sc.input_transcription
                and sc.input_transcription.text
            ):
                self.partial_transcript.emit(
                    f"[You]: {sc.input_transcription.text}"
                )

            # Turn complete
            if sc.turn_complete:
                speaking = False
                if not self._recording:
                    self._set_status("idle")

    # ------------------------------------------------------------------
    # Internal: push-to-talk helpers
    # ------------------------------------------------------------------

    async def _begin_turn(self) -> None:
        """Send ActivityStart, open mic, start send loop."""
        try:
            from google.genai import types

            # Clear leftover speaker audio so the user doesn't hear stale output
            self._spk_buffer.clear()
            self._vad.reset()

            await self._session.send_realtime_input(
                activity_start=types.ActivityStart()
            )
            self._start_mic()
            self._send_task = asyncio.create_task(self._mic_send_loop())
            self._set_status("listening")
            logger.info("Turn started (mic open)")
        except Exception as exc:
            logger.error("Failed to start turn: %s", exc)
            self.error_occurred.emit(f"Mic error: {exc}")
            self._recording = False

    async def _end_turn(self) -> None:
        """Stop mic, drain queue, send ActivityEnd."""
        try:
            self._stop_mic()
            self._vad.log_stats()

            # Cancel send task
            if self._send_task and not self._send_task.done():
                self._send_task.cancel()
                try:
                    await self._send_task
                except asyncio.CancelledError:
                    pass
                self._send_task = None

            # Drain leftover mic chunks
            while not self._mic_queue.empty():
                try:
                    self._mic_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            from google.genai import types

            await self._session.send_realtime_input(
                activity_end=types.ActivityEnd()
            )
            self._set_status("speaking")  # waiting for model response
            logger.info("Turn ended (mic closed), awaiting model response")
        except Exception as exc:
            logger.error("Failed to end turn: %s", exc)
            self.error_occurred.emit(f"Error ending turn: {exc}")

    async def _mic_send_loop(self) -> None:
        """Read int16 PCM from mic queue, filter through VAD, and stream to Gemini."""
        from google.genai import types

        mime = f"audio/pcm;rate={self._mic_rate}"
        try:
            while self._recording and self._session:
                try:
                    chunk: np.ndarray = await asyncio.wait_for(
                        self._mic_queue.get(), timeout=0.2
                    )
                    # VAD gating — only send frames classified as speech
                    frames = self._vad.process(chunk)
                    if frames is None:
                        continue

                    for frame in frames:
                        await self._session.send_realtime_input(
                            audio=types.Blob(
                                data=frame.tobytes(), mime_type=mime,
                            )
                        )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Mic send error: %s", exc)

    # ------------------------------------------------------------------
    # Internal: sounddevice — microphone
    # ------------------------------------------------------------------

    def _start_mic(self) -> None:
        """Open a 16 kHz mono int16 InputStream."""
        if self._mic_stream is not None:
            return

        loop = self._loop

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                logger.warning("Mic status: %s", status)
            if loop is not None and self._recording:
                # indata is (frames, 1) int16 — flatten and copy
                loop.call_soon_threadsafe(
                    self._mic_queue.put_nowait, indata.copy().flatten()
                )

        self._mic_stream = sd.InputStream(
            samplerate=self._mic_rate,
            channels=1,
            dtype="int16",
            blocksize=self._mic_block,
            callback=callback,
        )
        self._mic_stream.start()
        logger.info("Mic stream started (%d Hz, block=%d)", self._mic_rate, self._mic_block)

    def _stop_mic(self) -> None:
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
            self._mic_stream = None
            logger.info("Mic stream stopped")

    # ------------------------------------------------------------------
    # Internal: sounddevice — speaker
    # ------------------------------------------------------------------

    def _start_speaker_stream(self) -> None:
        """Open a 24 kHz mono int16 OutputStream that continuously
        pulls from ``_spk_buffer``.  Outputs silence when empty."""
        if self._spk_stream is not None:
            return

        spk_buf = self._spk_buffer  # capture for closure

        def callback(outdata: np.ndarray, frames: int, time_info, status):  # noqa: ARG001
            if status:
                logger.warning("Speaker status: %s", status)
            needed = frames * 2  # 2 bytes per int16 sample
            avail = spk_buf.available()
            if avail >= needed:
                raw = spk_buf.read(needed)
                outdata[:, 0] = np.frombuffer(raw, dtype=np.int16)
            elif avail > 0:
                raw = spk_buf.read(avail)
                n_samples = len(raw) // 2
                arr = np.frombuffer(raw, dtype=np.int16)
                outdata[:n_samples, 0] = arr
                outdata[n_samples:, 0] = 0
            else:
                outdata[:, 0] = 0

        self._spk_stream = sd.OutputStream(
            samplerate=self._spk_rate,
            channels=1,
            dtype="int16",
            blocksize=2048,  # ~85 ms at 24 kHz — smooth playback
            callback=callback,
        )
        self._spk_stream.start()
        logger.info("Speaker stream started (%d Hz)", self._spk_rate)

    def _stop_speaker_stream(self) -> None:
        if self._spk_stream is not None:
            try:
                self._spk_stream.stop()
                self._spk_stream.close()
            except Exception:
                pass
            self._spk_stream = None
            self._spk_buffer.clear()
            logger.info("Speaker stream stopped")

    # ------------------------------------------------------------------
    # Internal: cleanup
    # ------------------------------------------------------------------

    async def _cleanup(self) -> None:
        """Cancel tasks, close streams, tear down session."""
        self._recording = False
        self._stop_mic()
        self._stop_speaker_stream()

        if self._send_task and not self._send_task.done():
            self._send_task.cancel()

        if self._session_task and not self._session_task.done():
            self._session_task.cancel()
            try:
                await self._session_task
            except asyncio.CancelledError:
                pass

        self._session = None
        logger.info("GeminiLiveSpeechService shut down")
