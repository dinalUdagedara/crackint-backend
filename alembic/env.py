"""
Alembic environment: sync engine from config, SQLModel metadata from app.models.
"""

from __future__ import with_statement

import pathlib
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

# Prepend project root so app is importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import settings
from app.models import *  # noqa: F401, F403 - populate SQLModel.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Sync engine for migrations (Alembic uses sync)
sync_engine = create_engine(settings.DB_SYNC_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: only URL, no engine."""
    url = settings.DB_SYNC_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using the sync engine."""
    with sync_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
