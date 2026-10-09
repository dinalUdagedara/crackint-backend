"""
Application configuration via environment variables.
"""

from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production-min-32-chars"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Application settings loaded from .env or environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Crackint Backend API"
    API_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # "development" or "production". Production enforces a real JWT secret and a CORS allow-list.
    ENVIRONMENT: str = "development"
    # Comma-separated list of allowed browser origins (HTTP API and Socket.IO). "*" allows any (dev only).
    CORS_ORIGINS: str = "http://localhost:3000"

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

    # Resume–job fit agent: LLM analysis of CV vs job (fit score, summary, suggestions, location suitability)
    RESUME_JOB_FIT_LLM_ENABLED: bool = False
    RESUME_JOB_FIT_LLM_MODEL: str = "gpt-4o-mini"

    # Cover letter agent: LLM-based cover letter generation
    COVER_LETTER_AGENT_ENABLED: bool = True
    COVER_LETTER_AGENT_MODEL: str = "gpt-4o-mini"
    COVER_LETTER_AGENT_TEMPERATURE: float = 0.7

    # JWT authentication
    JWT_SECRET: str = DEFAULT_JWT_SECRET

    # Google OAuth (for POST /auth/google - verify ID token and create/link user)
    GOOGLE_CLIENT_ID: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

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
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed CORS_ORIGINS. ["*"] means any origin."""
        origins = [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]
        return ["*"] if "*" in origins else origins

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        """Refuse to start in production with an insecure secret or open CORS."""
        if not self.is_production:
            return self
        if self.JWT_SECRET == DEFAULT_JWT_SECRET or len(self.JWT_SECRET) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET must be set to a unique value of at least {MIN_JWT_SECRET_LENGTH} "
                "characters when ENVIRONMENT=production."
            )
        if "*" in self.cors_origins_list or not self.cors_origins_list:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins (not '*') when ENVIRONMENT=production."
            )
        return self

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
