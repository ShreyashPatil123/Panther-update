"""Gemini Live real-time speech-to-speech client.

Completely isolated from NVIDIAClient — uses Google's genai SDK
to manage a full-duplex audio session via WebSocket.
"""
import asyncio
import enum
from dataclasses import dataclass
from typing import AsyncIterator, Callable, List, Optional

import numpy as np
from loguru import logger


class GeminiLiveState(enum.Enum):
    """Session lifecycle states."""

    IDLE = "idle"
    CONNECTING = "connecting"
    ACTIVE = "active"
    ERROR = "error"


@dataclass
class GeminiLiveConfig:
    """Configuration for a Gemini Live session."""

    model: str = "gemini-2.0-flash-live-001"
    input_sample_rate: int = 16000  # 16kHz mono PCM16
    output_sample_rate: int = 24000  # 24kHz mono PCM16
    channels: int = 1
    chunk_duration_ms: int = 100  # send audio in 100ms chunks
    system_instruction: str = (
        "You are a helpful voice assistant called Panther. "
        "Respond naturally and conversationally. Keep responses concise."
    )
    voice_name: str = "Puck"


class GeminiLiveClient:
    """Manages a Gemini Live real-time voice session.

    Lifecycle:
        1. connect()       — establishes WebSocket session
        2. send_audio()    — called repeatedly with mic PCM chunks
        3. receive_audio() — async iterator yielding speaker PCM chunks
        4. disconnect()    — tears down session

    Audio format:
        Input:  16kHz, 16-bit PCM, mono (numpy int16 arrays)
        Output: 24kHz, 16-bit PCM, mono (numpy int16 arrays)
    """

    def __init__(self, api_key: str, config: Optional[GeminiLiveConfig] = None):
        self.api_key = api_key
        self.config = config or GeminiLiveConfig()
        self._state = GeminiLiveState.IDLE
        self._session = None
        self._client = None
        self._receive_task: Optional[asyncio.Task] = None
        self._output_queue: asyncio.Queue[Optional[np.ndarray]] = asyncio.Queue()
        self._state_callbacks: List[Callable[[GeminiLiveState], None]] = []
        self._error: Optional[str] = None

    @property
    def state(self) -> GeminiLiveState:
        """Current session state."""
        return self._state

    @property
    def error_message(self) -> Optional[str]:
        """Last error message, if any."""
        return self._error

    def on_state_change(self, callback: Callable[[GeminiLiveState], None]):
        """Register a callback for state transitions."""
        self._state_callbacks.append(callback)

    def _set_state(self, new_state: GeminiLiveState, error: Optional[str] = None):
        """Update state and notify callbacks."""
        self._state = new_state
        self._error = error
        for cb in self._state_callbacks:
            try:
                cb(new_state)
            except Exception:
                pass

    async def connect(self):
        """Establish a Gemini Live session."""
        if self._state == GeminiLiveState.ACTIVE:
            logger.warning("Already connected to Gemini Live")
            return

        self._set_state(GeminiLiveState.CONNECTING)
        try:
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=self.api_key)

            live_config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self.config.voice_name,
                        )
                    )
                ),
            )
            if self.config.system_instruction:
                live_config.system_instruction = types.Content(
                    parts=[types.Part(text=self.config.system_instruction)]
                )

            self._session = await self._client.aio.live.connect(
                model=self.config.model,
                config=live_config,
            )

            # Start background receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())

            self._set_state(GeminiLiveState.ACTIVE)
            logger.info("Gemini Live session connected")

        except ImportError:
            self._set_state(
                GeminiLiveState.ERROR,
                "google-genai package not installed. Run: pip install google-genai",
            )
            raise
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "UNAUTHENTICATED" in error_msg:
                error_msg = "Invalid Google API key. Please check your key in Settings."
            elif "403" in error_msg or "PERMISSION_DENIED" in error_msg:
                error_msg = "API key lacks Gemini Live access. Check your Google AI permissions."
            self._set_state(GeminiLiveState.ERROR, error_msg)
            logger.error(f"Gemini Live connect failed: {e}")
            raise

    async def send_audio(self, pcm_chunk: np.ndarray):
        """Send a chunk of mic audio to Gemini.

        Args:
            pcm_chunk: int16 numpy array, 16kHz mono
        """
        if self._state != GeminiLiveState.ACTIVE or self._session is None:
            return

        try:
            from google.genai import types

            raw_bytes = pcm_chunk.astype(np.int16).tobytes()
            await self._session.send_realtime_input(
                audio=types.Blob(
                    data=raw_bytes, mime_type="audio/pcm;rate=16000"
                )
            )
        except Exception as e:
            logger.error(f"Error sending audio to Gemini: {e}")
            self._set_state(GeminiLiveState.ERROR, f"Send error: {e}")

    async def send_image(self, jpeg_bytes: bytes):
        """Send a screen frame to Gemini during a live session.

        Args:
            jpeg_bytes: JPEG-encoded image bytes.
        """
        if self._state != GeminiLiveState.ACTIVE or self._session is None:
            return

        try:
            from google.genai import types

            await self._session.send_realtime_input(
                video=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
            )
        except Exception as e:
            logger.error(f"Error sending image to Gemini: {e}")

    async def send_text(self, text: str):
        """Send text context to Gemini during a live session.

        Used to inject OCR-extracted screen content as text context
        alongside the ongoing audio stream.

        Args:
            text: Text content to send (e.g., OCR output from screen capture)
        """
        if self._state != GeminiLiveState.ACTIVE or self._session is None:
            return

        try:
            await self._session.send_realtime_input(text=text)
        except Exception as e:
            logger.error(f"Error sending text to Gemini: {e}")

    async def _receive_loop(self):
        """Background task: read audio responses from Gemini, enqueue them."""
        try:
            async for response in self._session.receive():
                server_content = getattr(response, "server_content", None)
                if not server_content:
                    continue

                model_turn = getattr(server_content, "model_turn", None)
                if model_turn and model_turn.parts:
                    for part in model_turn.parts:
                        inline_data = getattr(part, "inline_data", None)
                        if inline_data and inline_data.data:
                            audio_array = np.frombuffer(
                                inline_data.data, dtype=np.int16
                            )
                            await self._output_queue.put(audio_array)

                # Check if turn is complete
                turn_complete = getattr(server_content, "turn_complete", False)
                if turn_complete:
                    await self._output_queue.put(None)  # sentinel

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Gemini Live receive error: {e}")
            self._set_state(GeminiLiveState.ERROR, f"Receive error: {e}")
            await self._output_queue.put(None)  # unblock consumer

    async def receive_audio(self) -> AsyncIterator[np.ndarray]:
        """Yield audio chunks from Gemini as they arrive.

        Yields:
            int16 numpy arrays at 24kHz mono.
            Iteration ends when session closes or turn completes.
        """
        while self._state == GeminiLiveState.ACTIVE:
            try:
                chunk = await asyncio.wait_for(
                    self._output_queue.get(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue
            if chunk is None:
                break
            yield chunk

    async def disconnect(self):
        """Tear down the Gemini Live session."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

        self._client = None

        # Drain the output queue
        while not self._output_queue.empty():
            try:
                self._output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        self._set_state(GeminiLiveState.IDLE)
        logger.info("Gemini Live session disconnected")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
