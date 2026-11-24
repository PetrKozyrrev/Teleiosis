import pytest
from alembic.autogenerate import compare_metadata
from sqlalchemy import text, inspect

from app.db import Base
from tests.test_email_auth_migration import migration_db  # noqa: F401
from tests.test_organization_migration import schema_before_redesign


@pytest.mark.parametrize("migration_db", ["t0c2e4f6a8b9"], indirect=True)
def test_review_migration_preserves_existing_plan(migration_db):
    connection, migration = migration_db
    owner = connection.scalar(text("INSERT INTO users(email) VALUES ('review-migration@example.com') RETURNING id"))
    connection.execute(text("INSERT INTO study_goals(user_id,name) VALUES (:id,'Synthetic')"), {"id": owner})
    migration.upgrade()
    assert compare_metadata(schema_before_redesign(connection), Base.metadata) == []
    migration.downgrade()
    assert "review_cards" not in inspect(connection).get_table_names()
    migration.upgrade()
    assert connection.scalar(text("SELECT name FROM study_goals")) == "Synthetic"
