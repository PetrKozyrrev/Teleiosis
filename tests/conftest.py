import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models  # noqa: F401
from app.config import settings
from app.db import Base
from app.deps import get_db
from app.main import app


@pytest.fixture(scope="session")
def engine():
    if not settings.test_database_url:
        pytest.fail("TEST_DATABASE_URL не задан в .env")
    if settings.test_database_url == settings.database_url:
        pytest.fail("Тестовая база не должна совпадать с рабочей")
    engine = create_engine(settings.test_database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session(engine):
    """Каждый тест работает в транзакции, которая откатывается в конце."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture()
def client(session, monkeypatch):
    """API-клиент, который работает в тестовой сессии (откатывается после теста)."""
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()