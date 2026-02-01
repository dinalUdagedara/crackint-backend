"""
Shared dependencies for API routes (e.g. database session).
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session; rollback on exception, close on exit."""
    async for session in db_session():
        yield session
