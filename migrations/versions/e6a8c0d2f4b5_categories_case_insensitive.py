"""categories: unique names ignoring case

Revision ID: e6a8c0d2f4b5
Revises: d5f7b9c1e3a4
Create Date: 2026-11-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a8c0d2f4b5'
down_revision: Union[str, Sequence[str], None] = 'd5f7b9c1e3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Дубли по регистру молча не правим: останавливаемся и просим решить вручную
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM ("
            "SELECT 1 FROM categories GROUP BY user_id, lower(name) HAVING count(*) > 1"
            ") AS d"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"Миграция остановлена: найдено групп категорий с одинаковым названием "
            f"без учёта регистра: {duplicates}. Переименуйте или удалите дубли вручную "
            f"и повторите."
        )

    op.drop_constraint('uq_categories_user_name', 'categories', type_='unique')
    op.create_index(
        'uq_categories_user_lower_name',
        'categories',
        ['user_id', sa.text('lower(name)')],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_categories_user_lower_name', table_name='categories')
    op.create_unique_constraint('uq_categories_user_name', 'categories', ['user_id', 'name'])