"""add topic_mastery table (per-user spaced repetition of weak topics)

Revision ID: 014
Revises: 013
Create Date: 2026-10-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "topic_mastery",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("current_timestamp(0)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("current_timestamp(0)"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_score", sa.Float(), nullable=True),
        sa.Column("avg_score", sa.Float(), nullable=True),
        sa.Column("box", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("next_due_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint("user_id", "topic", name="uq_topic_mastery_user_topic"),
    )
    op.create_index("ix_topic_mastery_id", "topic_mastery", ["id"])
    op.create_index("ix_topic_mastery_user_id", "topic_mastery", ["user_id"])
    op.create_index("ix_topic_mastery_next_due_at", "topic_mastery", ["next_due_at"])


def downgrade() -> None:
    op.drop_index("ix_topic_mastery_next_due_at", table_name="topic_mastery")
    op.drop_index("ix_topic_mastery_user_id", table_name="topic_mastery")
    op.drop_index("ix_topic_mastery_id", table_name="topic_mastery")
    op.drop_table("topic_mastery")
