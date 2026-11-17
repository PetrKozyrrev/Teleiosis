"""Distinguish web cookies from mobile bearer sessions.

Revision ID: k2a4b6c8d0e1
Revises: j1f3a5b7c9d0
"""
from alembic import op
import sqlalchemy as sa

revision = "k2a4b6c8d0e1"
down_revision = "j1f3a5b7c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("client_type", sa.Text(), nullable=False, server_default="web"))
    op.create_check_constraint("ck_auth_sessions_client_type", "auth_sessions", "client_type IN ('web', 'mobile')")


def downgrade() -> None:
    # A mobile token must never become a valid cookie after rollback.
    op.execute("DELETE FROM auth_sessions WHERE client_type = 'mobile'")
    op.drop_constraint("ck_auth_sessions_client_type", "auth_sessions", type_="check")
    op.drop_column("auth_sessions", "client_type")
