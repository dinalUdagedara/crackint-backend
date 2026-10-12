"""add llm_usage table (per-call LLM tokens, cost, latency)

Revision ID: 011
Revises: 010
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("current_timestamp(0)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("current_timestamp(0)"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["prep_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id"),
    )
    op.create_index("ix_llm_usage_id", "llm_usage", ["id"])
    op.create_index("ix_llm_usage_user_id", "llm_usage", ["user_id"])
    op.create_index("ix_llm_usage_session_id", "llm_usage", ["session_id"])
    op.create_index("ix_llm_usage_agent", "llm_usage", ["agent"])
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_created_at", table_name="llm_usage")
    op.drop_index("ix_llm_usage_agent", table_name="llm_usage")
    op.drop_index("ix_llm_usage_session_id", table_name="llm_usage")
    op.drop_index("ix_llm_usage_user_id", table_name="llm_usage")
    op.drop_index("ix_llm_usage_id", table_name="llm_usage")
    op.drop_table("llm_usage")
