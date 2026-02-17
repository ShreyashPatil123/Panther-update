"""Configuration management for NVIDIA AI Agent."""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # NVIDIA API Configuration
    nvidia_api_key: Optional[str] = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        alias="NVIDIA_BASE_URL",
    )
    default_model: str = Field(default="nvidia/kimi-k-2.5", alias="DEFAULT_MODEL")

    # Application Settings
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    db_path: Path = Field(default=Path("./data/agent.db"), alias="DB_PATH")
    chroma_path: Path = Field(default=Path("./data/chroma"), alias="CHROMA_PATH")

    # Speech Settings
    stt_model: str = Field(default="base.en", alias="STT_MODEL")
    tts_voice: str = Field(default="en_US-lessac-medium", alias="TTS_VOICE")

    # Security
    encrypt_storage: bool = Field(default=True, alias="ENCRYPT_STORAGE")
    local_processing_only: bool = Field(default=False, alias="LOCAL_PROCESSING_ONLY")

    # UI Settings
    window_width: int = 1400
    window_height: int = 900
    sidebar_width: int = 250

    # Feature flags
    speech_enabled: bool = True
    max_retries: int = 3


def load_config():
    """Load and return application configuration."""
    return Settings()
