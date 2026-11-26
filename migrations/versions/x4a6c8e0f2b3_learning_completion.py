"""Add standalone reflections and completion idempotency receipts."""

import sqlalchemy as sa
from alembic import op

revision = "x4a6c8e0f2b3"
down_revision = "w3f5b7d9e1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_reflections",
        sa.Column("content_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("thought", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"], ondelete="CASCADE"),
        sa.CheckConstraint("char_length(thought) BETWEEN 1 AND 4000", name="ck_content_reflection_thought"),
    )
    op.create_index("ix_reflection_owner_content", "content_reflections", ["user_id", "content_id"])
    op.create_table(
        "learning_completions",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("key", sa.Uuid(), primary_key=True),
        sa.Column("content_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_learning_completion_content", "learning_completions", ["content_id"])


def downgrade() -> None:
    changed = op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM content_reflections) OR EXISTS (SELECT 1 FROM learning_completions)"
    ))
    if changed:
        raise RuntimeError("Downgrade would discard reflections or completion receipts")
    op.drop_table("learning_completions")
    op.drop_table("content_reflections")
