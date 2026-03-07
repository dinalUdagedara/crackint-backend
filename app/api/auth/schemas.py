"""Request/response schemas for auth API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class RegisterRequest(BaseModel):
    """Body for user registration."""

    email: EmailStr = Field(..., description="User email (unique).")
    password: str = Field(..., min_length=8, description="Plain password (min 8 chars).")
    name: str = Field(..., min_length=1, description="Display name.")


class LoginRequest(BaseModel):
    """Body for login."""

    email: EmailStr = Field(..., description="User email.")
    password: str = Field(..., description="Plain password.")


class GoogleTokenRequest(BaseModel):
    """Body for Google login: Google OAuth ID token from the client."""

    id_token: str = Field(..., description="Google OAuth ID token from the frontend.")


class UserRead(BaseModel):
    """User payload returned in auth responses (no password)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    created_at: datetime


class TokenResponse(BaseModel):
    """Login response: access token and user info."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead
