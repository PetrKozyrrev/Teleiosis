"""users: last_digest_on

Revision ID: f7b9d1e3a5c6
Revises: e6a8c0d2f4b5
Create Date: 2026-11-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b9d1e3a5c6'
down_revision: Union[str, Sequence[str], None] = 'e6a8c0d2f4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('last_digest_on', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'last_digest_on')