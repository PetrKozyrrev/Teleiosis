"""Publish a standalone PDF material only after storage succeeds."""
import sqlalchemy as sa
from alembic import op

revision = "r8a0c2e4f6b7"
down_revision = "q7f9b1c3d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pdf_objects", sa.Column("creating", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.drop_constraint("ck_contents_url_or_note", "contents", type_="check")
    op.create_check_constraint("ck_contents_url_or_note", "contents",
                               "url IS NOT NULL OR note IS NOT NULL OR content_type = 'pdf'")


def downgrade():
    op.execute("""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM contents WHERE content_type = 'pdf')
          OR EXISTS (SELECT 1 FROM pdf_objects WHERE creating) THEN
            RAISE EXCEPTION 'Remove PDF materials and finish cleanup before downgrade';
        END IF;
    END $$;
    """)
    op.drop_constraint("ck_contents_url_or_note", "contents", type_="check")
    op.create_check_constraint("ck_contents_url_or_note", "contents", "url IS NOT NULL OR note IS NOT NULL")
    op.drop_column("pdf_objects", "creating")
