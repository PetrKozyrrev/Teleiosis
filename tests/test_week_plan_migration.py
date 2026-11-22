import pytest
from sqlalchemy import inspect, text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import Base
from tests.test_email_auth_migration import migration_db  # noqa: F401


@pytest.mark.parametrize("migration_db", ["s9b1d3e5f7a8"], indirect=True)
def test_week_plan_roundtrip_preserves_pdf_and_session(migration_db):
    connection, migration = migration_db
    user_id = connection.scalar(text("INSERT INTO users (email) VALUES ('week-migration@example.com') RETURNING id"))
    connection.execute(text("INSERT INTO contents (user_id,title,content_type) VALUES (:id,'Synthetic PDF','pdf')"), {"id": user_id})
    connection.execute(text("INSERT INTO auth_sessions (user_id,token_hash,client_type,expires_at) "
                            "VALUES (:id,:hash,'mobile',now()+interval '1 day')"), {"id": user_id, "hash": "e" * 64})
    migration.upgrade()
    assert compare_metadata(MigrationContext.configure(connection, opts={"include_object":
        lambda obj, name, kind, reflected, compare: kind != "table" or name not in
        ("review_cards", "review_answers", "review_creations")}), Base.metadata) == []
    migration.downgrade()
    assert "study_tasks" not in inspect(connection).get_table_names()
    migration.upgrade()
    assert connection.scalar(text("SELECT count(*) FROM study_tasks")) == 0
    assert connection.scalar(text("SELECT content_type FROM contents")) == "pdf"
    assert connection.scalar(text("SELECT client_type FROM auth_sessions")) == "mobile"
