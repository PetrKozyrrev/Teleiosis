"""users: email login, password hash, consent

Revision ID: a3c5e7f9b1d2
Revises: bfae7459debc
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c5e7f9b1d2'
down_revision: Union[str, Sequence[str], None] = 'bfae7459debc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('email', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('consent_version', sa.Text(), nullable=True))

    op.alter_column('users', 'telegram_id', existing_type=sa.BigInteger(), nullable=True)

    # Имя совпадает с тем, которое PostgreSQL даёт для unique=True в модели
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.create_check_constraint(
        'ck_users_login_method', 'users',
        'email IS NOT NULL OR telegram_id IS NOT NULL',
    )
    op.create_check_constraint('ck_users_email_lower', 'users', 'email = lower(email)')
    op.create_check_constraint('ck_users_email_len', 'users', 'char_length(email) <= 254')
    op.create_check_constraint(
        'ck_users_password_needs_email', 'users',
        'password_hash IS NULL OR email IS NOT NULL',
    )
    op.create_check_constraint(
        'ck_users_consent_pair', 'users',
        '(consent_at IS NULL) = (consent_version IS NULL)',
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Без telegram_id пользователь после отката станет недопустимым.
    # Удалять чужие данные молча нельзя, поэтому откат останавливается.
    orphans = op.get_bind().execute(
        sa.text("SELECT count(*) FROM users WHERE telegram_id IS NULL")
    ).scalar()
    if orphans:
        raise RuntimeError(
            f"Откат невозможен: {orphans} пользователей без telegram_id. "
            "Удалите их вручную, если это тестовые данные."
        )

    op.drop_constraint('ck_users_consent_pair', 'users', type_='check')
    op.drop_constraint('ck_users_password_needs_email', 'users', type_='check')
    op.drop_constraint('ck_users_email_len', 'users', type_='check')
    op.drop_constraint('ck_users_email_lower', 'users', type_='check')
    op.drop_constraint('ck_users_login_method', 'users', type_='check')
    op.drop_constraint('users_email_key', 'users', type_='unique')

    op.alter_column('users', 'telegram_id', existing_type=sa.BigInteger(), nullable=False)

    op.drop_column('users', 'consent_version')
    op.drop_column('users', 'consent_at')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'email')