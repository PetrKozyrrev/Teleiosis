import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db import Base
from tests.test_email_auth_migration import migration_db  # noqa: F401


@pytest.mark.parametrize("migration_db", ["y5b7d9f1a3c4"], indirect=True)
def test_learning_event_migration_preserves_materials_without_fabricating_history(migration_db):
    connection, migration = migration_db
    connection.execute(text("INSERT INTO users (email) VALUES ('historical@example.com')"))
    connection.execute(text("""
        INSERT INTO contents(user_id,title,note,status,studied_at)
        SELECT id,'Historical','Keep','studied',now() FROM users
    """))
    migration.upgrade()
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    assert connection.scalar(text("SELECT count(*) FROM learning_events")) == 0
    connection.execute(text("""
        INSERT INTO learning_events(user_id,name,dedupe_key,occurred_at,local_day)
        SELECT id,'today_viewed','fixture',now(),CURRENT_DATE FROM users
    """))
    with pytest.raises(RuntimeError, match="discard"):
        migration.downgrade()
    connection.execute(text("DELETE FROM learning_events"))
    migration.downgrade()
    assert "learning_events" not in inspect(connection).get_table_names()
    assert connection.execute(text("SELECT status,note FROM contents")).one() == ("studied", "Keep")
    migration.upgrade()
    assert connection.scalar(text("SELECT count(*) FROM learning_events")) == 0
