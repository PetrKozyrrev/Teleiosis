"""Remove Telegram identity; require email for every account.

Revision ID: j1f3a5b7c9d0
Revises: i0e2a4b6d8f9
"""

from alembic import op
import sqlalchemy as sa

revision = "j1f3a5b7c9d0"
down_revision = "i0e2a4b6d8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Hold the lock until commit so no old client can insert another account
    # without email between this check and the NOT NULL constraint.
    op.execute("LOCK TABLE users IN ACCESS EXCLUSIVE MODE")
    missing_email = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM users WHERE email IS NULL")
    )
    if missing_email:
        raise RuntimeError(
            f"Migration stopped: {missing_email} accounts have no email. "
            "Assign real email addresses to these accounts before retrying; "
            "no accounts or content have been deleted."
        )
    op.drop_constraint("ck_users_login_method", "users", type_="check")
    op.drop_constraint("ck_users_password_needs_email", "users", type_="check")
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=False)
    op.drop_column("users", "telegram_id")
    op.drop_column("users", "username")


def downgrade() -> None:
    # Schema rollback cannot recover removed Telegram identifiers.
    op.add_column("users", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("users_telegram_id_key", "users", ["telegram_id"])
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        "ck_users_login_method", "users",
        "email IS NOT NULL OR telegram_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_users_password_needs_email", "users",
        "password_hash IS NULL OR email IS NOT NULL",
    )
