"""
Auth endpoints: register, login, google, me.
"""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.schemas import GoogleTokenRequest, LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.api.deps import get_current_user, get_db
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.common.http_response_model import CommonResponse
from app.config import settings
from app.models import User

router = APIRouter()


@router.post(
    "/register",
    response_model=CommonResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    name="Register",
    summary="Register a new user.",
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db),
):
    """Create a new user. Returns 400 if email already exists."""
    result = await session.execute(select(User).where(User.email == body.email))
    if result.scalars().one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = User(
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return CommonResponse(
        success=True,
        message="User registered successfully",
        payload=UserRead.model_validate(user),
    )


@router.post(
    "/login",
    response_model=CommonResponse[TokenResponse],
    name="Login",
    summary="Login with email and password; returns JWT and user.",
)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),
):
    """Return access_token and user. Use Authorization: Bearer <access_token> for protected routes."""
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalars().one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=expires,
    )
    return CommonResponse(
        success=True,
        message="Login successful",
        payload=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserRead.model_validate(user),
        ),
    )


@router.post(
    "/google",
    response_model=CommonResponse[TokenResponse],
    name="Google login",
    summary="Exchange a Google OAuth ID token for a backend JWT. Creates user if not exists.",
)
async def google_login(
    body: GoogleTokenRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Accept a Google ID token from the frontend (obtained after Google OAuth sign-in).
    Verifies the token, then looks up or creates the user by email. Returns the same
    shape as POST /login: access_token, token_type, user.
    Requires GOOGLE_CLIENT_ID in config (same as frontend OAuth client ID).
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured (GOOGLE_CLIENT_ID missing)",
        )
    try:
        idinfo = id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Google token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    email = idinfo.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account has no email",
        )
    name = idinfo.get("name") or email.split("@")[0]

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().one_or_none()
    if user is None:
        # Create user; OAuth users get a random unguessable password (they can only sign in via Google)
        user = User(
            email=email,
            name=name,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=expires,
    )
    return CommonResponse(
        success=True,
        message="Login successful",
        payload=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserRead.model_validate(user),
        ),
    )


@router.get(
    "/me",
    response_model=CommonResponse[UserRead],
    name="Current user",
    summary="Return the authenticated user.",
)
async def me(
    current_user: User = Depends(get_current_user),
):
    """Requires valid Bearer token."""
    return CommonResponse(
        success=True,
        message="Current user",
        payload=UserRead.model_validate(current_user),
    )
