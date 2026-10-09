import logging
import uuid
from typing import Any, Optional

import socketio
from fastapi import HTTPException
from sqlalchemy import select

from app.auth.jwt import decode_token
from app.config import settings
from app.database import SessionLocal
from app.models import User

logger = logging.getLogger(__name__)

_cors = "*" if settings.cors_origins_list == ["*"] else settings.cors_origins_list
sio_server = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=_cors)


def create_sio_app(other_app=None):
    return socketio.ASGIApp(
        socketio_server=sio_server,
        other_asgi_app=other_app,
        socketio_path="/ws/socket.io",
    )


def extract_token(environ: dict, auth: Optional[dict]) -> Optional[str]:
    """Token from the Socket.IO auth payload ({"token": ...}) or an Authorization: Bearer header."""
    if isinstance(auth, dict):
        token = auth.get("token")
        if isinstance(token, str) and token.strip():
            return token.strip()
    header = environ.get("HTTP_AUTHORIZATION") or ""
    if header.startswith("Bearer ") and header[7:].strip():
        return header[7:].strip()
    return None


async def user_exists(user_id: uuid.UUID) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(select(User.id).where(User.id == user_id))
        return result.scalar_one_or_none() is not None


async def authenticate(environ: dict, auth: Optional[dict]) -> Optional[uuid.UUID]:
    """Return the user id for a valid token belonging to an existing user, else None."""
    token = extract_token(environ, auth)
    if not token:
        return None
    try:
        payload: dict[str, Any] = decode_token(token)
        user_id = uuid.UUID(str(payload.get("sub")))
    except (HTTPException, ValueError):
        return None
    if not await user_exists(user_id):
        return None
    return user_id


async def get_socket_user_id(sid: str) -> Optional[uuid.UUID]:
    """User id stored for an authenticated socket, or None."""
    try:
        session = await sio_server.get_session(sid)
    except KeyError:
        return None
    return session.get("user_id")


@sio_server.event
async def connect(sid, environ, auth=None):
    user_id = await authenticate(environ, auth)
    if user_id is None:
        logger.info("Socket connection refused (unauthenticated) %s", sid)
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    await sio_server.save_session(sid, {"user_id": user_id})
    logger.info("Socket connected %s (user %s)", sid, user_id)
