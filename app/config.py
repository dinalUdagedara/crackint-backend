"""
Application configuration via environment variables.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env or environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    APP_NAME: str = "Crackint Backend API"
    API_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # NER model: directory where saved model, tokenizer, and config are stored
    RESUME_NER_LOAD_DIR: Optional[str] = None
    JOB_POSTER_NER_LOAD_DIR: Optional[str] = None

    # Upload limits for resume/job PDFs (MB)
    MAX_UPLOAD_SIZE_MB: int = 10


settings = Settings()
