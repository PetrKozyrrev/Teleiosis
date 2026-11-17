import pytest
from sqlalchemy import text

from tests.test_email_auth_migration import migration_db  # noqa: F401


@pytest.mark.parametrize("migration_db", ["k2a4b6c8d0e1"], indirect=True)
def test_mobile_migration_preserves_web_and_revokes_mobile_on_downgrade(migration_db):
    connection, migration = migration_db
    user_id = connection.scalar(text("INSERT INTO users (email) VALUES ('migration@example.com') RETURNING id"))
    connection.execute(text("INSERT INTO auth_sessions (user_id, token_hash, expires_at) VALUES (:user, :hash, now()+interval '1 day')"), {"user": user_id, "hash": "a"*64})
    migration.upgrade()
    assert connection.scalar(text("SELECT client_type FROM auth_sessions")) == "web"
    connection.execute(text("INSERT INTO auth_sessions (user_id, token_hash, client_type, expires_at) VALUES (:user, :hash, 'mobile', now()+interval '1 day')"), {"user": user_id, "hash": "b"*64})
    migration.downgrade()
    assert connection.scalars(text("SELECT token_hash FROM auth_sessions")).all() == ["a"*64]
    migration.upgrade()
    assert connection.scalar(text("SELECT client_type FROM auth_sessions")) == "web"
