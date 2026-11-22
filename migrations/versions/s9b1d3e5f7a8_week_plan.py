"""Owner-scoped goals, weekly budgets, dated tasks and their history."""
from alembic import op
import sqlalchemy as sa

revision = "s9b1d3e5f7a8"
down_revision = "r8a0c2e4f6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("study_goals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("id", "user_id", name="uq_study_goal_owner"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_study_goal_name"))
    op.create_index("uq_study_goal_name", "study_goals", ["user_id", sa.text("lower(name)")], unique=True)
    op.create_table("week_budgets",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("week", sa.Date(), primary_key=True),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint("minutes BETWEEN 1 AND 10080", name="ck_week_budget_minutes"))
    op.create_table("study_tasks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("goal_id", sa.BigInteger(), nullable=False),
        sa.Column("content_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["goal_id", "user_id"], ["study_goals.id", "study_goals.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("goal_id", "content_id", name="uq_study_task_material"),
        sa.CheckConstraint("minutes BETWEEN 1 AND 1440", name="ck_study_task_minutes"),
        sa.CheckConstraint("priority BETWEEN 1 AND 3", name="ck_study_task_priority"))
    op.create_index("ix_study_task_owner_day", "study_tasks", ["user_id", "day"])
    op.create_table("study_task_events",
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("study_tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    for table in ("study_task_events", "study_tasks", "week_budgets", "study_goals"):
        op.drop_table(table)
