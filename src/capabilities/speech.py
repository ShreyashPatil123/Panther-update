"""Speech interface with STT and TTS."""
import asyncio
import io
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, List, Optional

import numpy as np
from loguru import logger


@dataclass
class SpeechConfig:
    """Speech configuration."""
    # STT settings
    stt_model: str = "base.en"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_language: str = "en"
    stt_beam_size: int = 5

    # TTS settings
    tts_voice: str = "en_US-lessac-medium"
    tts_speaker_id: Optional[int] = None

    # Audio settings
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration: float = 0.5  # seconds

    # VAD settings
    vad_enabled: bool = True
    vad_threshold: float = 0.5
    silence_duration: float = 2.0  # seconds of silence to end recording


class SpeechInterface:
    """Speech-to-text and text-to-speech interface."""

    def __init__(self, config: Optional[SpeechConfig] = None):
        """Initialize speech interface.

        Args:
            config: Speech configuration
        """
        self.config = config or SpeechConfig()

        # Models (loaded on demand)
        self._whisper_model = None
        self._piper_voice = None

        # Audio recording state
        self._is_recording = False
        self._recording_buffer: List[np.ndarray] = []
        self._audio_queue: asyncio.Queue = asyncio.Queue()

        # Callbacks
        self._on_speech_start: Optional[Callable] = None
        self._on_speech_end: Optional[Callable] = None
        self._on_interim_result: Optional[Callable] = None

    async def initialize(self):
        """Initialize speech models."""
        logger.info("Initializing speech interface")

        # Import libraries on demand
        try:
            import sounddevice as sd
            self._sd = sd
        except ImportError:
            logger.error("sounddevice not installed. Install with: pip install sounddevice")
            raise

        logger.info("Speech interface initialized")

    def _load_whisper(self):
        """Load Whisper model."""
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info(f"Loading Whisper model: {self.config.stt_model}")
                self._whisper_model = WhisperModel(
                    self.config.stt_model,
                    device=self.config.stt_device,
                    compute_type=self.config.stt_compute_type,
                )
                logger.info("Whisper model loaded")
            except ImportError:
                logger.error("faster-whisper not installed. Install with: pip install faster-whisper")
                raise

    def _load_piper(self):
        """Load Piper TTS voice."""
        if self._piper_voice is None:
            try:
                from piper import PiperVoice
                logger.info(f"Loading Piper voice: {self.config.tts_voice}")

                # Download voice if not exists
                self._ensure_voice_downloaded()

                self._piper_voice = PiperVoice.load(self.config.tts_voice)
                logger.info("Piper voice loaded")
            except ImportError:
                logger.error("piper-tts not installed. Install with: pip install piper-tts")
                raise

    def _ensure_voice_downloaded(self):
        """Ensure TTS voice is downloaded."""
        # This would check and download voice files
        # For now, assume they're available
        pass

    async def speech_to_text(
        self,
        audio_data: np.ndarray,
        language: Optional[str] = None,
    ) -> str:
        """Convert speech to text.

        Args:
            audio_data: Audio samples as numpy array
            language: Language code (auto-detect if None)

        Returns:
            Transcribed text
        """
        self._load_whisper()

        logger.info("Transcribing audio...")

        # Ensure correct format
        if audio_data.dtype != np.float32:
            audio_float = audio_data.astype(np.float32) / 32768.0
        else:
            audio_float = audio_data

        # Transcribe
        segments, info = self._whisper_model.transcribe(
            audio_float,
            beam_size=self.config.stt_beam_size,
            language=language or self.config.stt_language,
        )

        # Collect text
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text)

        text = " ".join(text_parts).strip()
        logger.info(f"Transcription: {text[:100]}...")

        return text

    async def speech_to_text_stream(
        self,
        audio_chunks: AsyncIterator[np.ndarray],
    ) -> AsyncIterator[str]:
        """Stream speech to text.

        Args:
            audio_chunks: Async iterator of audio chunks

        Yields:
            Transcribed text chunks
        """
        # Buffer audio
        buffer = []
        async for chunk in audio_chunks:
            buffer.append(chunk)

        if buffer:
            audio_data = np.concatenate(buffer)
            text = await self.speech_to_text(audio_data)
            yield text

    async def text_to_speech(
        self,
        text: str,
        output_path: Optional[Path] = None,
    ) -> np.ndarray:
        """Convert text to speech.

        Args:
            text: Text to synthesize
            output_path: Optional path to save audio

        Returns:
            Audio data as numpy array
        """
        self._load_piper()

        logger.info(f"Synthesizing speech: {text[:50]}...")

        # Synthesize
        audio_data = []
        for audio_bytes in self._piper_voice.synthesize_stream_raw(text):
            audio_data.extend(audio_bytes)

        # Convert to numpy
        audio_array = np.array(audio_data, dtype=np.int16)

        # Save if path provided
        if output_path:
            await self._save_audio(audio_array, output_path)

        return audio_array

    async def text_to_speech_stream(
        self,
        text: str,
    ) -> AsyncIterator[np.ndarray]:
        """Stream text to speech.

        Args:
            text: Text to synthesize

        Yields:
            Audio chunks
        """
        self._load_piper()

        chunk_size = 1024
        audio_data = await self.text_to_speech(text)

        # Yield chunks
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            yield chunk
            await asyncio.sleep(0.01)

    async def _save_audio(self, audio_data: np.ndarray, path: Path):
        """Save audio to WAV file.

        Args:
            audio_data: Audio samples
            path: Output path
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(self.config.channels)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.config.sample_rate)
            wav_file.writeframes(audio_data.tobytes())

        logger.info(f"Saved audio to: {path}")

    async def play_audio(self, audio_data: np.ndarray):
        """Play audio through speakers.

        Args:
            audio_data: Audio samples
        """
        try:
            self._sd.play(audio_data, self.config.sample_rate)
            self._sd.wait()
        except Exception as e:
            logger.error(f"Error playing audio: {e}")
            raise

    async def record_audio(
        self,
        duration: Optional[float] = None,
        silence_timeout: Optional[float] = None,
    ) -> np.ndarray:
        """Record audio from microphone.

        Args:
            duration: Recording duration in seconds (None for manual stop)
            silence_timeout: Stop after silence for this many seconds

        Returns:
            Recorded audio
        """
        logger.info("Starting audio recording...")
        self._is_recording = True

        try:
            if duration:
                # Fixed duration recording
                recording = self._sd.rec(
                    int(duration * self.config.sample_rate),
                    samplerate=self.config.sample_rate,
                    channels=self.config.channels,
                    dtype=np.int16,
                )
                self._sd.wait()
                return recording.flatten()
            else:
                # Continuous recording with VAD
                return await self._record_with_vad(silence_timeout)

        except Exception as e:
            logger.error(f"Error recording audio: {e}")
            raise
        finally:
            self._is_recording = False

    async def _record_with_vad(
        self,
        silence_timeout: Optional[float] = None,
    ) -> np.ndarray:
        """Record audio with voice activity detection.

        Args:
            silence_timeout: Stop after silence for this many seconds

        Returns:
            Recorded audio
        """
        silence_timeout = silence_timeout or self.config.silence_duration

        buffer = []
        is_speaking = False
        silence_start = None

        # Create input stream
        def callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Audio status: {status}")
            buffer.append(indata.copy())

        stream = self._sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=np.int16,
            callback=callback,
        )

        with stream:
            if self._on_speech_start:
                self._on_speech_start()

            while self._is_recording:
                await asyncio.sleep(0.1)

                if not buffer:
                    continue

                # Process recent audio for VAD
                recent = np.concatenate(buffer[-10:]) if len(buffer) > 10 else np.concatenate(buffer)
                volume = np.abs(recent).mean()

                if volume > 500:  # Simple threshold
                    if not is_speaking:
                        is_speaking = True
                        silence_start = None
                        logger.debug("Speech detected")
                else:
                    if is_speaking:
                        if silence_start is None:
                            silence_start = asyncio.get_event_loop().time()
                        elif asyncio.get_event_loop().time() - silence_start > silence_timeout:
                            logger.info(f"Silence detected for {silence_timeout}s, stopping")
                            break

        if self._on_speech_end:
            self._on_speech_end()

        if buffer:
            return np.concatenate(buffer).flatten()
        return np.array([], dtype=np.int16)

    async def listen_and_transcribe(
        self,
        duration: Optional[float] = None,
        silence_timeout: Optional[float] = None,
    ) -> str:
        """Record and transcribe speech.

        Args:
            duration: Recording duration
            silence_timeout: Silence timeout for VAD

        Returns:
            Transcribed text
        """
        audio = await self.record_audio(duration, silence_timeout)
        if len(audio) == 0:
            return ""

        text = await self.speech_to_text(audio)
        return text

    async def synthesize_and_play(self, text: str):
        """Synthesize and play speech.

        Args:
            text: Text to speak
        """
        audio = await self.text_to_speech(text)
        await self.play_audio(audio)

    def stop_recording(self):
        """Stop current recording."""
        self._is_recording = False
        logger.info("Recording stopped")

    def set_callbacks(
        self,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable] = None,
        on_interim_result: Optional[Callable] = None,
    ):
        """Set speech callbacks.

        Args:
            on_speech_start: Called when speech starts
            on_speech_end: Called when speech ends
            on_interim_result: Called with interim transcription
        """
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_interim_result = on_interim_result

    async def calibrate_microphone(self, duration: float = 2.0):
        """Calibrate microphone for ambient noise.

        Args:
            duration: Calibration duration
        """
        logger.info(f"Calibrating microphone for {duration}s...")

        recording = self._sd.rec(
            int(duration * self.config.sample_rate),
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=np.int16,
        )
        self._sd.wait()

        # Calculate noise floor
        noise_level = np.abs(recording).mean()
        logger.info(f"Noise level: {noise_level}")

        return noise_level

    async def get_audio_devices(self) -> dict:
        """Get available audio devices.

        Returns:
            Dictionary of devices
        """
        devices = {
            "input": [],
            "output": [],
        }

        try:
            device_list = self._sd.query_devices()
            for i, device in enumerate(device_list):
                device_info = {
                    "index": i,
                    "name": device["name"],
                    "channels": device.get("max_input_channels", 0) or device.get("max_output_channels", 0),
                }

                if device.get("max_input_channels", 0) > 0:
                    devices["input"].append(device_info)
                if device.get("max_output_channels", 0) > 0:
                    devices["output"].append(device_info)
        except Exception as e:
            logger.error(f"Error getting audio devices: {e}")

        return devices

    async def set_input_device(self, device_index: int):
        """Set input device.

        Args:
            device_index: Device index
        """
        self._sd.default.device[0] = device_index
        logger.info(f"Set input device to index {device_index}")

    async def set_output_device(self, device_index: int):
        """Set output device.

        Args:
            device_index: Device index
        """
        self._sd.default.device[1] = device_index
        logger.info(f"Set output device to index {device_index}")

    async def shutdown(self):
        """Shutdown speech interface."""
        self.stop_recording()

        self._whisper_model = None
        self._piper_voice = None

        logger.info("Speech interface shut down")


class WakeWordDetector:
    """Wake word detection for hands-free activation."""

    def __init__(self, wake_word: str = "hey assistant", sensitivity: float = 0.8):
        """Initialize wake word detector.

        Args:
            wake_word: Wake word phrase
            sensitivity: Detection sensitivity
        """
        self.wake_word = wake_word.lower()
        self.sensitivity = sensitivity
        self._is_listening = False

    async def start_listening(self, callback: Callable):
        """Start listening for wake word.

        Args:
            callback: Called when wake word detected
        """
        self._is_listening = True

        # This would use a proper wake word detection library
        # For now, simplified implementation
        logger.info(f"Listening for wake word: {self.wake_word}")

        # Simulated wake word detection
        # In production, use something like Porcupine or similar

    def stop_listening(self):
        """Stop listening."""
        self._is_listening = False
        logger.info("Wake word detection stopped")

    def check_wake_word(self, text: str) -> bool:
        """Check if text contains wake word.

        Args:
            text: Transcribed text

        Returns:
            True if wake word detected
        """
        return self.wake_word in text.lower()
