"""
Database connection: async PostgreSQL engine and session for dependency injection.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings

async_engine = create_async_engine(
    settings.DB_URL,
    echo=settings.DB_ECHO,
    future=True,
    pool_pre_ping=True,
    connect_args={"server_settings": {"application_name": "Crackint Backend API"}},
)

SessionLocal = sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session; rollback on exception, close on exit."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
