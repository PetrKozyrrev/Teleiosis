"""Add a first-party, private ledger of typed learning events."""

import sqlalchemy as sa
from alembic import op

revision = "y5b7d9f1a3c4"
down_revision = "x4a6c8e0f2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("dedupe_key", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_day", sa.Date(), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=True),
        sa.Column("visit_id", sa.Uuid(), nullable=True),
        sa.Column("budget_minutes", sa.Integer(), nullable=True),
        sa.Column("has_results", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("user_id", "name", "dedupe_key", name="uq_learning_event_once"),
        sa.CheckConstraint("budget_minutes IN (5,15,30,60)", name="ck_learning_event_budget"),
    )
    op.create_index("ix_learning_event_occurred", "learning_events", ["occurred_at"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM learning_events)")):
        raise RuntimeError("Downgrade would discard recorded pilot events")
    op.drop_table("learning_events")
