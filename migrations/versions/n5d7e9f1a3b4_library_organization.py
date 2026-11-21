"""Owner-scoped tags, collections and material membership.

Revision ID: n5d7e9f1a3b4
Revises: m4c6d8e0f2a3
"""
from alembic import op
import sqlalchemy as sa

revision = "n5d7e9f1a3b4"
down_revision = "m4c6d8e0f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_contents_id_user", "contents", ["id", "user_id"])
    op.create_table(
        "library_groups",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id", "user_id", name="uq_library_groups_id_user"),
        sa.CheckConstraint("kind IN ('tag', 'collection')", name="ck_library_groups_kind"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 50", name="ck_library_groups_name_len"),
    )
    op.create_index("uq_library_groups_owner_kind_name", "library_groups",
                    ["user_id", "kind", sa.text("lower(name)")], unique=True)
    op.create_table(
        "content_groups",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("content_id", sa.BigInteger(), primary_key=True),
        sa.Column("group_id", sa.BigInteger(), primary_key=True),
        sa.ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"],
                                ondelete="CASCADE", name="fk_content_groups_content_owner"),
        sa.ForeignKeyConstraint(["group_id", "user_id"], ["library_groups.id", "library_groups.user_id"],
                                ondelete="CASCADE", name="fk_content_groups_group_owner"),
    )
    op.create_index("ix_content_groups_owner_group", "content_groups", ["user_id", "group_id", "content_id"])


def downgrade():
    op.drop_table("content_groups")
    op.drop_table("library_groups")
    op.drop_constraint("uq_contents_id_user", "contents", type_="unique")
