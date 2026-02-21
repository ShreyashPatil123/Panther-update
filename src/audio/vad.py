"""Energy-based Voice Activity Detection for real-time audio streams.

Lightweight VAD using only numpy — zero external dependencies.
Designed for 16 kHz, int16, mono PCM in 1024-sample (64 ms) blocks.

Sits between the microphone and the Gemini Live API to filter
silence/noise frames and reduce unnecessary API traffic.
"""

from collections import deque
from dataclasses import dataclass

import numpy as np
from loguru import logger


@dataclass
class VADConfig:
    """Tunable VAD parameters.

    All frame-count parameters are relative to the block size.
    At 16 kHz with 1024-sample blocks, one frame = 64 ms.
    """

    # Speech is detected when RMS energy exceeds noise_floor * threshold_ratio.
    threshold_ratio: float = 3.0

    # Continue sending for this many frames after energy drops below
    # threshold.  Prevents cutting off trailing consonants.
    # 5 frames * 64 ms = 320 ms
    hangover_frames: int = 5

    # Ring-buffer depth of recent silence frames.  Flushed on speech
    # onset so the very beginning of a word is not clipped.
    # 4 frames * 64 ms = 256 ms
    pre_buffer_frames: int = 4

    # First N frames of each turn are used exclusively to estimate
    # the ambient noise floor.  Audio during calibration is NOT sent.
    # 6 frames * 64 ms ≈ 384 ms
    calibration_frames: int = 6

    # Exponential moving average smoothing for noise floor updates
    # during silence.  Closer to 1.0 = slower adaptation.
    noise_ema_alpha: float = 0.95

    # Absolute minimum RMS floor to prevent threshold collapse in a
    # perfectly silent room.  50 is well below real speech (~500-5000).
    min_noise_floor: float = 50.0

    # Master on/off switch.  When False, process() passes everything through.
    enabled: bool = True


class EnergyVAD:
    """Frame-by-frame energy-based Voice Activity Detector.

    Usage::

        vad = EnergyVAD()                # or EnergyVAD(VADConfig(...))
        vad.reset()                       # call at the start of each PTT turn

        for chunk in mic_chunks:
            frames = vad.process(chunk)
            if frames is not None:
                for f in frames:
                    send_to_gemini(f)

        vad.log_stats()                   # end-of-turn summary
    """

    def __init__(self, config: VADConfig | None = None) -> None:
        self.cfg = config or VADConfig()
        self._noise_floor: float = 0.0
        self._frame_count: int = 0
        self._hangover_remaining: int = 0
        self._is_speech: bool = False
        self._pre_buffer: deque[np.ndarray] = deque(maxlen=self.cfg.pre_buffer_frames)

        # Stats
        self._total_frames: int = 0
        self._sent_frames: int = 0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.cfg.enabled = value

    def reset(self) -> None:
        """Reset all state.  Call at the START of each push-to-talk turn."""
        self._noise_floor = 0.0
        self._frame_count = 0
        self._hangover_remaining = 0
        self._is_speech = False
        self._pre_buffer = deque(maxlen=self.cfg.pre_buffer_frames)
        self._total_frames = 0
        self._sent_frames = 0

    def process(self, chunk: np.ndarray) -> list[np.ndarray] | None:
        """Process one audio frame.

        Args:
            chunk: int16 numpy array, typically 1024 samples (64 ms at 16 kHz).

        Returns:
            A list of numpy arrays to send (may include pre-buffered frames
            on speech onset), or None if the frame is silence.
        """
        if not self.cfg.enabled:
            return [chunk]

        self._total_frames += 1
        self._frame_count += 1
        rms = self._compute_rms(chunk)

        # ── Phase 1: Calibration ──────────────────────────────────────
        if self._frame_count <= self.cfg.calibration_frames:
            if self._frame_count == 1:
                self._noise_floor = rms
            else:
                n = self._frame_count
                self._noise_floor = (self._noise_floor * (n - 1) + rms) / n
            self._noise_floor = max(self._noise_floor, self.cfg.min_noise_floor)
            self._pre_buffer.append(chunk)
            return None

        # ── Phase 2: Steady-state detection ───────────────────────────
        threshold = self._noise_floor * self.cfg.threshold_ratio
        is_loud = rms > threshold

        if is_loud:
            if not self._is_speech:
                # Speech onset — flush pre-buffer
                self._is_speech = True
                frames_to_send = list(self._pre_buffer)
                self._pre_buffer.clear()
                frames_to_send.append(chunk)
                self._hangover_remaining = self.cfg.hangover_frames
                self._sent_frames += len(frames_to_send)
                return frames_to_send
            # Continuing speech
            self._hangover_remaining = self.cfg.hangover_frames
            self._sent_frames += 1
            return [chunk]

        # Below threshold
        # Adapt noise floor during silence only
        if not self._is_speech:
            self._noise_floor = (
                self.cfg.noise_ema_alpha * self._noise_floor
                + (1 - self.cfg.noise_ema_alpha) * rms
            )
            self._noise_floor = max(self._noise_floor, self.cfg.min_noise_floor)

        if self._is_speech:
            if self._hangover_remaining > 0:
                self._hangover_remaining -= 1
                self._sent_frames += 1
                return [chunk]
            # Hangover expired — transition to silence
            self._is_speech = False
            # Adapt noise floor now that we're back in silence
            self._noise_floor = (
                self.cfg.noise_ema_alpha * self._noise_floor
                + (1 - self.cfg.noise_ema_alpha) * rms
            )
            self._noise_floor = max(self._noise_floor, self.cfg.min_noise_floor)

        self._pre_buffer.append(chunk)
        return None

    def log_stats(self) -> None:
        """Log end-of-turn filtering statistics."""
        if self._total_frames == 0:
            return

        filtered = self._total_frames - self._sent_frames
        pct_filtered = (filtered / self._total_frames) * 100
        pct_sent = (self._sent_frames / self._total_frames) * 100
        duration_s = self._total_frames * 0.064  # 64 ms per frame

        logger.info(
            "VAD stats: {:.1f}s total | {} sent ({:.0f}%) | "
            "{} filtered ({:.0f}%) | noise_floor={:.0f}",
            duration_s,
            self._sent_frames,
            pct_sent,
            filtered,
            pct_filtered,
            self._noise_floor,
        )

    # ------------------------------------------------------------------ #
    # Private
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_rms(chunk: np.ndarray) -> float:
        """Root-mean-square energy of an int16 PCM chunk."""
        samples = chunk.astype(np.float64)
        return float(np.sqrt(np.mean(samples * samples)))
