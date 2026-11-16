from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.deps import get_db
from app.main import create_app


@pytest.mark.parametrize("production", [False, True])
def test_docs_are_private_in_production(monkeypatch, production):
    monkeypatch.setattr(settings, "app_env", "prod" if production else "dev")
    with TestClient(create_app()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == (404 if production else 200)
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/app/login.html").status_code == 200


@pytest.mark.parametrize("failure", [False, True])
def test_readiness_reports_db_failure_without_leaking_details(failure):
    db = Mock()
    if failure:
        db.execute.side_effect = OperationalError("SECRET-DATABASE-ADDRESS", {}, Exception("secret"))
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    with TestClient(application) as client:
        response = client.get("/ready")
        assert response.status_code == (503 if failure else 200)
        assert response.json() == {"status": "unavailable" if failure else "ready"}
        assert response.headers["cache-control"] == "no-store"
        assert "secret" not in response.text.lower()
        # Liveness must stay available while the database is down.
        assert client.get("/health").status_code == 200


def test_readiness_queries_real_database(client):
    assert client.get("/ready").status_code == 200
