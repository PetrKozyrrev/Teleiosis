"""Version editable fields and store durable, account-scoped submission receipts."""
from alembic import op
import sqlalchemy as sa

revision = "l3b5c7d9e1f2"
down_revision = "k2a4b6c8d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contents", sa.Column("version", sa.BigInteger(), server_default=sa.text("1"), nullable=False))
    op.execute("""
    CREATE OR REPLACE FUNCTION increment_content_version() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF ROW(NEW.title, NEW.note, NEW.category_id, NEW.status)
            IS DISTINCT FROM ROW(OLD.title, OLD.note, OLD.category_id, OLD.status) THEN
            NEW.version := OLD.version + 1;
        END IF;
        RETURN NEW;
    END;
    $$;
    """)
    op.execute("""
    CREATE TRIGGER contents_version BEFORE UPDATE ON contents
    FOR EACH ROW EXECUTE FUNCTION increment_content_version();
    """)
    op.create_table(
        "content_submissions",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("content_id", sa.BigInteger(), nullable=False),
        sa.Column("duplicate", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("content_submissions")
    op.execute("DROP TRIGGER contents_version ON contents")
    op.execute("DROP FUNCTION increment_content_version()")
    op.drop_column("contents", "version")
