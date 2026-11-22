"""Manual review cards and durable answer receipts."""
from alembic import op
import sqlalchemy as sa

revision = "t0c2e4f6a8b9"
down_revision = "s9b1d3e5f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("review_cards",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("content_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("takeaway", sa.Text(), nullable=False, server_default=""),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stage", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"], ondelete="CASCADE"),
        sa.CheckConstraint("char_length(question) BETWEEN 1 AND 500", name="ck_review_question"),
        sa.CheckConstraint("char_length(answer) BETWEEN 1 AND 4000", name="ck_review_answer"),
        sa.CheckConstraint("char_length(takeaway) <= 4000", name="ck_review_takeaway"),
        sa.CheckConstraint("stage BETWEEN 0 AND 7", name="ck_review_stage"))
    op.create_index("ix_review_owner_due", "review_cards", ["user_id", "due_on", "id"])
    op.create_table("review_creations",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False))
    op.create_table("review_answers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("card_id", sa.BigInteger(), sa.ForeignKey("review_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("previous_version", sa.BigInteger(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("card_id", "key", name="uq_review_answer_key"),
        sa.CheckConstraint("rating IN ('again','remembered')", name="ck_review_rating"))
    op.create_index("ix_review_answer_card_id", "review_answers", ["card_id", "id"])


def downgrade():
    op.drop_table("review_answers")
    op.drop_table("review_creations")
    op.drop_table("review_cards")
