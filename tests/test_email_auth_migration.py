"""Exercise real migrations in an isolated, rolled-back PostgreSQL schema."""

from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from alembic.autogenerate import compare_metadata
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import Base


@pytest.fixture
def migration_db(engine):
    with engine.connect() as connection, connection.begin():
        schema = f"migration_test_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        scripts = ScriptDirectory.from_config(Config("alembic.ini"))
        revisions = list(reversed(list(scripts.walk_revisions())))
        context = MigrationContext.configure(connection)
        try:
            with Operations.context(context):
                for revision in revisions[:-1]:
                    revision.module.upgrade()
                yield connection, revisions[-1].module
        finally:
            connection.rollback()


def test_upgrade_matches_models_and_preserves_account_data(migration_db):
    connection, migration = migration_db
    user_id = connection.scalar(text(
        "INSERT INTO users (email, telegram_id, username) "
        "VALUES ('ivan@example.com', 42, 'old_name') RETURNING id"
    ))
    connection.execute(text(
        "INSERT INTO contents (user_id, title, note) VALUES (:id, 'Saved', 'Keep me')"
    ), {"id": user_id})
    connection.execute(text(
        "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
        "VALUES (:id, :hash, now() + interval '1 day')"
    ), {"id": user_id, "hash": "a" * 64})

    migration.upgrade()
    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    assert "telegram_id" not in columns
    assert "username" not in columns
    assert connection.scalar(text("SELECT email FROM users WHERE id = :id"), {"id": user_id}) == "ivan@example.com"
    assert connection.scalar(text("SELECT note FROM contents")) == "Keep me"
    assert connection.scalar(text("SELECT count(*) FROM auth_sessions")) == 1
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []

    migration.downgrade()
    assert "telegram_id" in {c["name"] for c in inspect(connection).get_columns("users")}
    assert connection.scalar(text("SELECT note FROM contents")) == "Keep me"
    migration.upgrade()
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_upgrade_refuses_accounts_without_email_before_changing_schema(migration_db):
    connection, migration = migration_db
    connection.execute(text("INSERT INTO users (telegram_id) VALUES (42)"))
    with pytest.raises(RuntimeError, match="1 accounts have no email"):
        migration.upgrade()
    assert "telegram_id" in {c["name"] for c in inspect(connection).get_columns("users")}
    assert connection.scalar(text("SELECT telegram_id FROM users")) == 42
    connection.execute(text("UPDATE users SET email = 'ivan@example.com'"))
    migration.upgrade()
    assert connection.scalar(text("SELECT count(*) FROM users")) == 1


def test_fresh_database_requires_email(migration_db):
    connection, migration = migration_db
    migration.upgrade()
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(text("INSERT INTO users DEFAULT VALUES"))
