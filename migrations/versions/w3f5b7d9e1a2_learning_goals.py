"""Extend existing study goals and backfill independent material memberships."""

import sqlalchemy as sa
from alembic import op

revision = "w3f5b7d9e1a2"
down_revision = "v2e4a6b8c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("study_goals", sa.Column("result", sa.Text()))
    op.add_column("study_goals", sa.Column("status", sa.Text(), nullable=False, server_default="active"))
    op.add_column("study_goals", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.create_check_constraint("ck_study_goal_status", "study_goals", "status IN ('active','completed','archived')")
    op.create_index("ix_study_goal_owner_status", "study_goals", ["user_id", "status", "id"])
    op.create_table(
        "study_goal_materials",
        sa.Column("goal_id", sa.BigInteger(), primary_key=True),
        sa.Column("content_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["goal_id", "user_id"], ["study_goals.id", "study_goals.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_study_goal_material_owner_content", "study_goal_materials", ["user_id", "content_id", "goal_id"])
    op.execute("""
        INSERT INTO study_goal_materials (goal_id, content_id, user_id)
        SELECT goal_id, content_id, user_id FROM study_tasks
    """)


def downgrade() -> None:
    changed = op.get_bind().scalar(sa.text("""
        SELECT EXISTS (SELECT 1 FROM study_goals WHERE result IS NOT NULL OR status <> 'active')
            OR EXISTS (
                SELECT goal_id, content_id FROM study_goal_materials
                EXCEPT SELECT goal_id, content_id FROM study_tasks
            ) OR EXISTS (
                SELECT goal_id, content_id FROM study_tasks
                EXCEPT SELECT goal_id, content_id FROM study_goal_materials
            )
    """))
    if changed:
        raise RuntimeError("Downgrade would discard goal results, statuses or material memberships")
    op.drop_table("study_goal_materials")
    op.drop_index("ix_study_goal_owner_status", table_name="study_goals")
    op.drop_constraint("ck_study_goal_status", "study_goals", type_="check")
    for column in ("version", "status", "result"):
        op.drop_column("study_goals", column)
