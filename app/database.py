"""
Database connection stub for future use (session history, users, etc.).
No DB is configured in the initial phase; resume extract flow does not persist data.
"""

# When you add a real DB (e.g. PostgreSQL or SQLite), replace this with:
# - create_async_engine / SessionLocal
# - async def db_session() -> AsyncGenerator[AsyncSession, None]
# and wire it in config via DATABASE_URL
