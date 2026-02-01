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

    # Database (PostgreSQL)
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "crackint_db"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = ""
    DB_ECHO: bool = False

    # NER model: directory where saved model, tokenizer, and config are stored
    RESUME_NER_LOAD_DIR: Optional[str] = None
    JOB_POSTER_NER_LOAD_DIR: Optional[str] = None

    # Upload limits for resume/job PDFs (MB)
    MAX_UPLOAD_SIZE_MB: int = 10

    @property
    def DB_URL(self) -> str:
        """Async PostgreSQL URL for SQLAlchemy (asyncpg)."""
        return (
            f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    @property
    def DB_SYNC_URL(self) -> str:
        """Sync PostgreSQL URL for Alembic migrations."""
        return (
            f"postgresql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )


settings = Settings()
