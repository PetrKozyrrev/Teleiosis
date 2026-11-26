import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db import Base
from tests.test_email_auth_migration import migration_db  # noqa: F401


@pytest.mark.parametrize("migration_db", ["w3f5b7d9e1a2"], indirect=True)
def test_migration_preserves_goals_tasks_and_history_and_refuses_lossy_downgrade(migration_db):
    connection, migration = migration_db
    connection.execute(text("INSERT INTO users (email) VALUES ('goals-migration@example.com')"))
    connection.execute(text("INSERT INTO study_goals (user_id, name) SELECT id, 'Old goal' FROM users"))
    connection.execute(text("INSERT INTO contents (user_id,title,note) SELECT id,'Old material','Keep' FROM users"))
    connection.execute(text("""
        INSERT INTO study_tasks (user_id, goal_id, content_id, day, minutes, priority)
        SELECT g.user_id, g.id, c.id, '2026-11-23', 15, 2 FROM study_goals g JOIN contents c USING (user_id)
    """))
    connection.execute(text("INSERT INTO study_task_events(task_id,version,kind,day) SELECT id,1,'created',day FROM study_tasks"))
    before = connection.execute(text("SELECT * FROM study_tasks")).all()
    migration.upgrade()
    def include(obj, name, kind, reflected, compare_to):
        return kind != "table" or name not in {"content_reflections", "learning_completions", "learning_events"}

    assert compare_metadata(MigrationContext.configure(connection, opts={"include_object": include}), Base.metadata) == []
    assert connection.execute(text("SELECT result,status,version FROM study_goals")).one() == (None, "active", 1)
    assert connection.scalar(text("SELECT count(*) FROM study_goal_materials")) == 1
    connection.execute(text("UPDATE study_goals SET status='archived'"))
    with pytest.raises(RuntimeError, match="discard"):
        migration.downgrade()
    connection.execute(text("UPDATE study_goals SET status='active'"))
    connection.execute(text("DELETE FROM study_goal_materials"))
    with pytest.raises(RuntimeError, match="discard"):
        migration.downgrade()
    connection.execute(text("INSERT INTO study_goal_materials SELECT goal_id,content_id,user_id FROM study_tasks"))
    migration.downgrade()
    assert "study_goal_materials" not in inspect(connection).get_table_names()
    assert connection.execute(text("SELECT * FROM study_tasks")).all() == before
    assert connection.scalar(text("SELECT count(*) FROM study_task_events")) == 1
    migration.upgrade()
    assert connection.scalar(text("SELECT count(*) FROM study_goal_materials")) == 1
