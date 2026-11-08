"""rate limit events

Revision ID: b7d2f4a6c8e1
Revises: a3c5e7f9b1d2
Create Date: 2026-11-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2f4a6c8e1'
down_revision: Union[str, Sequence[str], None] = 'a3c5e7f9b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('rate_limit_events',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('bucket', sa.Text(), nullable=False),
    sa.Column('key_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('char_length(key_hash) = 64', name='ck_rate_limit_hash_len'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rate_limit_lookup', 'rate_limit_events', ['bucket', 'key_hash', 'created_at'], unique=False)
    op.create_index('ix_rate_limit_created', 'rate_limit_events', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_rate_limit_created', table_name='rate_limit_events')
    op.drop_index('ix_rate_limit_lookup', table_name='rate_limit_events')
    op.drop_table('rate_limit_events')