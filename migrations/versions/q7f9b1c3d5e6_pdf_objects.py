"""Private PDF object reservations and lifecycle.

Revision ID: q7f9b1c3d5e6
Revises: p6e8f0a2b4c5
"""
import sqlalchemy as sa
from alembic import op

revision = "q7f9b1c3d5e6"
down_revision = "p6e8f0a2b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pdf_objects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("content_id", sa.BigInteger()),
        sa.Column("charged_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"],
                                ondelete="SET NULL", name="fk_pdf_objects_content_owner"),
        sa.UniqueConstraint("content_id", name="uq_pdf_objects_content"),
        sa.UniqueConstraint("user_id", "digest", name="uq_pdf_objects_owner_digest"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 10485760", name="ck_pdf_objects_size"),
        sa.CheckConstraint("(user_id IS NULL) = (content_id IS NULL)", name="ck_pdf_objects_ownership"),
    )
    op.create_index("ix_pdf_objects_cleanup", "pdf_objects", ["created_at", "id"],
                    postgresql_where=sa.text("published IS FALSE OR user_id IS NULL"))
    op.create_index("ix_pdf_objects_charged_user", "pdf_objects", ["charged_user_id"])


def downgrade():
    op.execute("""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pdf_objects) THEN
            RAISE EXCEPTION 'PDF object ledger must be empty before downgrade';
        END IF;
    END $$;
    """)
    op.drop_table("pdf_objects")
