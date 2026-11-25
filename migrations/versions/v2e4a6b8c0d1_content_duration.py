"""Store automatically measured video length and text size."""

import sqlalchemy as sa
from alembic import op

revision = "v2e4a6b8c0d1"
down_revision = "u1d3f5a7b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contents", sa.Column("video_duration_seconds", sa.Integer(), nullable=True))
    op.add_column("contents", sa.Column("text_character_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("contents", "text_character_count")
    op.drop_column("contents", "video_duration_seconds")
