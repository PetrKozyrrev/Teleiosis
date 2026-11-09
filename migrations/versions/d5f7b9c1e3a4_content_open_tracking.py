"""content open tracking

Revision ID: d5f7b9c1e3a4
Revises: c4e6a8b0d2f3
Create Date: 2026-11-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5f7b9c1e3a4'
down_revision: Union[str, Sequence[str], None] = 'c4e6a8b0d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('contents', sa.Column('last_opened_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contents', sa.Column('open_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.create_check_constraint('ck_contents_open_count', 'contents', 'open_count >= 0')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_contents_open_count', 'contents', type_='check')
    op.drop_column('contents', 'open_count')
    op.drop_column('contents', 'last_opened_at')