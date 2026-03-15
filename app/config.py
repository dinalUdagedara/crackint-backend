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
    # If set and RESUME_NER_LOAD_DIR is missing, download from Google Drive at startup
    RESUME_NER_GDRIVE_FOLDER_ID: Optional[str] = None  # folder (multiple files)
    RESUME_NER_GDRIVE_FILE_ID: Optional[str] = None   # single zip file containing the model
    JOB_POSTER_NER_LOAD_DIR: Optional[str] = None

    # Upload limits for resume/job PDFs (MB)
    MAX_UPLOAD_SIZE_MB: int = 10

    # Resume entity AI agent (optional validation/correction after NER)
    RESUME_ENTITY_AGENT_ENABLED: bool = False
    # Job entity AI agent (optional validation/correction after NER)
    JOB_ENTITY_AGENT_ENABLED: bool = False
    OPENAI_API_KEY: Optional[str] = None

    # Session Q&A agent: question generation + answer evaluation (interview prep chat)
    SESSION_QA_AGENT_ENABLED: bool = False
    SESSION_QA_AGENT_MODEL: str = "gpt-4o-mini"
    SESSION_QA_AGENT_TEMPERATURE: float = 0.7

    # CV scoring agent: LLM-based CV strength analysis (PDF/image or text)
    CV_SCORING_ENABLED: bool = False
    CV_SCORING_MODEL: str = "gpt-4o-mini"

    # Resume–job fit agent: LLM analysis of CV vs job posting (fit score, summary, suggestions)
    RESUME_JOB_FIT_LLM_ENABLED: bool = False
    RESUME_JOB_FIT_LLM_MODEL: str = "gpt-4o-mini"

    # Cover letter agent: LLM-based cover letter generation
    COVER_LETTER_AGENT_ENABLED: bool = True
    COVER_LETTER_AGENT_MODEL: str = "gpt-4o-mini"
    COVER_LETTER_AGENT_TEMPERATURE: float = 0.7

    # JWT authentication
    JWT_SECRET: str = "change-me-in-production-min-32-chars"

    # Google OAuth (for POST /auth/google - verify ID token and create/link user)
    GOOGLE_CLIENT_ID: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # AWS
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"

    # S3 uploads (cover images, etc.). If set, POST /uploads/image will upload to this bucket.
    S3_UPLOADS_BUCKET: Optional[str] = None
    # Region for uploads bucket (defaults to AWS_DEFAULT_REGION if not set)
    S3_UPLOADS_REGION: Optional[str] = None
    # Max size for cover/image uploads in MB (default 5)
    MAX_COVER_IMAGE_SIZE_MB: int = 5

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
