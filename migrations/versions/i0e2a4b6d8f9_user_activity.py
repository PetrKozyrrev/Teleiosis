"""user activity days

Revision ID: i0e2a4b6d8f9
Revises: h9d1f3a5c7e8
Create Date: 2026-11-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i0e2a4b6d8f9'
down_revision: Union[str, Sequence[str], None] = 'h9d1f3a5c7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_activity',
    sa.Column('user_id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'day')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_activity')