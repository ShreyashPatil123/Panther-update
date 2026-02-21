"""Configuration management for NVIDIA AI Agent."""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the project root (where this package lives)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # NVIDIA API Configuration
    nvidia_api_key: Optional[str] = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        alias="NVIDIA_BASE_URL",
    )
    default_model: str = Field(default="meta/llama-3.1-8b-instruct", alias="DEFAULT_MODEL")

    # Google API Configuration (for Gemini Live voice)
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")

    # Application Settings
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    db_path: Path = Field(default=Path("./data/agent.db"), alias="DB_PATH")
    chroma_path: Path = Field(default=Path("./data/chroma"), alias="CHROMA_PATH")

    # Speech Settings
    stt_model: str = Field(default="base.en", alias="STT_MODEL")
    tts_voice: str = Field(default="en_US-lessac-medium", alias="TTS_VOICE")

    # Screen Capture
    screen_capture_vision: bool = Field(default=False, alias="SCREEN_CAPTURE_VISION")
    screen_capture_gemini: bool = Field(default=False, alias="SCREEN_CAPTURE_GEMINI")
    screen_capture_monitor: int = Field(default=0, alias="SCREEN_CAPTURE_MONITOR")
    screen_capture_interval: int = Field(default=3, alias="SCREEN_CAPTURE_INTERVAL")

    # Security
    encrypt_storage: bool = Field(default=True, alias="ENCRYPT_STORAGE")
    local_processing_only: bool = Field(default=False, alias="LOCAL_PROCESSING_ONLY")

    # UI Settings
    window_width: int = 1400
    window_height: int = 900
    sidebar_width: int = 250

    # Voice Activity Detection
    vad_enabled: bool = Field(default=True, alias="VAD_ENABLED")

    # Feature flags
    speech_enabled: bool = True
    max_retries: int = 3


def load_config():
    """Load and return application configuration."""
    return Settings()
