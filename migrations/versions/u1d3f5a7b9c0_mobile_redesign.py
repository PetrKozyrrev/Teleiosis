"""Add reading preferences and version changes to a material's URL."""

import sqlalchemy as sa
from alembic import op

revision = "u1d3f5a7b9c0"
down_revision = "t0c2e4f6a8b9"
branch_labels = None
depends_on = None


def update_material_trigger(include_url: bool) -> None:
    new_url, old_url = (", NEW.url", ", OLD.url") if include_url else ("", "")
    op.execute(f"""
    CREATE OR REPLACE FUNCTION increment_content_version() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF ROW(NEW.title, NEW.note, NEW.category_id, NEW.status{new_url})
            IS DISTINCT FROM ROW(OLD.title, OLD.note, OLD.category_id, OLD.status{old_url}) THEN
            NEW.version := OLD.version + 1;
        END IF;
        RETURN NEW;
    END;
    $$
    """)


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(80), nullable=True))
    op.add_column("users", sa.Column("weekly_reading_goal", sa.Integer(), server_default=sa.text("5"), nullable=False))
    op.create_check_constraint("ck_users_weekly_reading_goal", "users", "weekly_reading_goal BETWEEN 1 AND 100")
    op.create_index("ix_contents_user_studied", "contents", ["user_id", "studied_at"])
    update_material_trigger(True)


def downgrade() -> None:
    update_material_trigger(False)
    op.drop_index("ix_contents_user_studied", table_name="contents")
    op.drop_constraint("ck_users_weekly_reading_goal", "users", type_="check")
    op.drop_column("users", "weekly_reading_goal")
    op.drop_column("users", "display_name")
