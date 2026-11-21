"""Account-local library import receipts.

Revision ID: p6e8f0a2b4c5
Revises: n5d7e9f1a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "p6e8f0a2b4c5"
down_revision = "n5d7e9f1a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "library_imports",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("digest", sa.Text(), primary_key=True),
        sa.Column("summary", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("library_imports")
