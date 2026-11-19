"""Account/session-bound RuStore registrations and durable push delivery ledger."""
from alembic import op
import sqlalchemy as sa

revision = "m4c6d8e0f2a3"
down_revision = "l3b5c7d9e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_push_devices_token_hash"),
    )
    op.create_table(
        "push_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("push_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_id", sa.BigInteger(), sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reminder_id", sa.BigInteger(), sa.ForeignKey("reminders.id", ondelete="CASCADE")),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reason", sa.Text()),
        sa.UniqueConstraint("device_id", "event_key", name="uq_push_deliveries_event_device"),
        sa.CheckConstraint("status IN ('pending','sending','retry_wait','accepted','cancelled','expired','failed')", name="ck_push_deliveries_status"),
    )
    op.create_index("ix_push_deliveries_due", "push_deliveries", ["status", "next_attempt_at"])


def downgrade():
    op.drop_table("push_deliveries")
    op.drop_table("push_devices")
