import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db import Base
from tests.test_email_auth_migration import migration_db  # noqa: F401


@pytest.mark.parametrize("migration_db", ["x4a6c8e0f2b3"], indirect=True)
def test_completion_migration_preserves_old_notes_and_refuses_lossy_downgrade(migration_db):
    connection, migration = migration_db
    connection.execute(text("INSERT INTO users(email) VALUES ('note-migration@example.com')"))
    connection.execute(text("INSERT INTO contents(user_id,title,note) SELECT id,'Synthetic','Keep this note' FROM users"))
    migration.upgrade()
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    connection.execute(text("INSERT INTO content_reflections(content_id,user_id,thought) SELECT id,user_id,'Takeaway' FROM contents"))
    with pytest.raises(RuntimeError, match="discard"):
        migration.downgrade()
    connection.execute(text("DELETE FROM content_reflections"))
    migration.downgrade()
    assert "learning_completions" not in inspect(connection).get_table_names()
    assert connection.scalar(text("SELECT note FROM contents")) == "Keep this note"
    migration.upgrade()
    assert connection.scalar(text("SELECT COUNT(*) FROM content_reflections")) == 0
