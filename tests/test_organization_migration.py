import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db import Base
from tests.test_email_auth_migration import migration_db  # noqa: F401


def schema_before(connection, *tables):
    def include_object(_object, name, type_, _reflected, _compare_to):
        return type_ != "table" or name not in tables
    return MigrationContext.configure(connection, opts={"include_object": include_object})


@pytest.mark.parametrize("migration_db", ["n5d7e9f1a3b4"], indirect=True)
def test_organization_migration_preserves_legacy_material_and_session(migration_db):
    connection, migration = migration_db
    owner = connection.scalar(text("INSERT INTO users (email) VALUES ('org-migration@example.com') RETURNING id"))
    content = connection.scalar(text("INSERT INTO contents (user_id,title,note) VALUES (:owner,'Legacy','Preserve') RETURNING id"), {"owner": owner})
    connection.execute(text("INSERT INTO auth_sessions (user_id,token_hash,client_type,expires_at) VALUES (:owner,:hash,'mobile',now()+interval '1 day')"), {"owner": owner, "hash": "c" * 64})
    migration.upgrade()
    assert compare_metadata(schema_before(connection, "library_imports", "pdf_objects"), Base.metadata) == []
    tag = connection.scalar(text("INSERT INTO library_groups (user_id,kind,name) VALUES (:owner,'tag','Migrated') RETURNING id"), {"owner": owner})
    connection.execute(text("INSERT INTO content_groups(user_id,content_id,group_id) VALUES (:owner,:content,:tag)"), {"owner": owner, "content": content, "tag": tag})
    migration.downgrade()
    assert "library_groups" not in inspect(connection).get_table_names()
    assert connection.scalar(text("SELECT note FROM contents WHERE id=:content"), {"content": content}) == "Preserve"
    assert connection.scalar(text("SELECT client_type FROM auth_sessions")) == "mobile"
    migration.upgrade()
    assert connection.scalar(text("SELECT count(*) FROM library_groups")) == 0
    assert connection.scalar(text("SELECT version FROM contents WHERE id=:content"), {"content": content}) == 1
    assert compare_metadata(schema_before(connection, "library_imports", "pdf_objects"), Base.metadata) == []


@pytest.mark.parametrize("migration_db", ["p6e8f0a2b4c5"], indirect=True)
def test_import_migration_preserves_existing_library_and_memberships(migration_db):
    connection, migration = migration_db
    owner = connection.scalar(text("INSERT INTO users (email) VALUES ('import-migration@example.com') RETURNING id"))
    content = connection.scalar(text("INSERT INTO contents (user_id,title,note) VALUES (:owner,'Legacy','Preserve') RETURNING id"), {"owner": owner})
    tag = connection.scalar(text("INSERT INTO library_groups (user_id,kind,name) VALUES (:owner,'tag','Existing') RETURNING id"), {"owner": owner})
    connection.execute(text("INSERT INTO content_groups(user_id,content_id,group_id) VALUES (:owner,:content,:tag)"),
                       {"owner": owner, "content": content, "tag": tag})

    migration.upgrade()
    assert compare_metadata(schema_before(connection, "pdf_objects"), Base.metadata) == []
    connection.execute(text("INSERT INTO library_imports(user_id,digest,summary) VALUES (:owner,:digest,'{}')"),
                       {"owner": owner, "digest": "d" * 64})
    migration.downgrade()
    assert "library_imports" not in inspect(connection).get_table_names()
    assert connection.execute(text("SELECT user_id, content_id, group_id FROM content_groups")).one() == (owner, content, tag)
    assert connection.scalar(text("SELECT note FROM contents WHERE id=:content"), {"content": content}) == "Preserve"
    migration.upgrade()
    assert connection.scalar(text("SELECT count(*) FROM library_imports")) == 0
    assert compare_metadata(schema_before(connection, "pdf_objects"), Base.metadata) == []
