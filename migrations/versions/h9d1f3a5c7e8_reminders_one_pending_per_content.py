"""reminders: one pending reminder per content

Revision ID: h9d1f3a5c7e8
Revises: g8c0e2f4b6d7
Create Date: 2026-11-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h9d1f3a5c7e8'
down_revision: Union[str, Sequence[str], None] = 'g8c0e2f4b6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Дубли молча не правим: останавливаемся и просим решить вручную
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM ("
            "SELECT 1 FROM reminders WHERE status = 'pending' "
            "GROUP BY content_id HAVING count(*) > 1"
            ") AS d"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"Миграция остановлена: у {duplicates} материалов больше одного "
            "ожидающего напоминания. Отмените лишние вручную и повторите."
        )

    op.create_index(
        'uq_reminders_content_pending',
        'reminders',
        ['content_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'uq_reminders_content_pending',
        table_name='reminders',
        postgresql_where=sa.text("status = 'pending'"),
    )