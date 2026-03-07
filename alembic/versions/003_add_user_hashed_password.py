"""add user hashed_password

Revision ID: 003
Revises: 002
Create Date: 2026-02-18

Existing users will have an empty placeholder; they must reset password to log in.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("hashed_password", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("users", "hashed_password")
