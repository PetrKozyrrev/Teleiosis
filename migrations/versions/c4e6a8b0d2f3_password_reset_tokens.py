"""password reset tokens

Revision ID: c4e6a8b0d2f3
Revises: b7d2f4a6c8e1
Create Date: 2026-11-08 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e6a8b0d2f3'
down_revision: Union[str, Sequence[str], None] = 'b7d2f4a6c8e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('password_reset_tokens',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('char_length(token_hash) = 64', name='ck_password_reset_hash_len'),
    sa.CheckConstraint('expires_at > created_at', name='ck_password_reset_expiry'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_password_reset_user', 'password_reset_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_password_reset_user', table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')