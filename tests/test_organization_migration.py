import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db import Base
from tests.test_email_auth_migration import migration_db  # noqa: F401


@pytest.mark.parametrize("migration_db", ["n5d7e9f1a3b4"], indirect=True)
def test_organization_migration_preserves_legacy_material_and_session(migration_db):
    connection, migration = migration_db
    owner = connection.scalar(text("INSERT INTO users (email) VALUES ('org-migration@example.com') RETURNING id"))
    content = connection.scalar(text("INSERT INTO contents (user_id,title,note) VALUES (:owner,'Legacy','Preserve') RETURNING id"), {"owner": owner})
    connection.execute(text("INSERT INTO auth_sessions (user_id,token_hash,client_type,expires_at) VALUES (:owner,:hash,'mobile',now()+interval '1 day')"), {"owner": owner, "hash": "c" * 64})
    migration.upgrade()
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    tag = connection.scalar(text("INSERT INTO library_groups (user_id,kind,name) VALUES (:owner,'tag','Migrated') RETURNING id"), {"owner": owner})
    connection.execute(text("INSERT INTO content_groups(user_id,content_id,group_id) VALUES (:owner,:content,:tag)"), {"owner": owner, "content": content, "tag": tag})
    migration.downgrade()
    assert "library_groups" not in inspect(connection).get_table_names()
    assert connection.scalar(text("SELECT note FROM contents WHERE id=:content"), {"content": content}) == "Preserve"
    assert connection.scalar(text("SELECT client_type FROM auth_sessions")) == "mobile"
    migration.upgrade()
    assert connection.scalar(text("SELECT count(*) FROM library_groups")) == 0
    assert connection.scalar(text("SELECT version FROM contents WHERE id=:content"), {"content": content}) == 1
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
