import pytest
from sqlalchemy import func, select

from app.models import AuthSession, User
from app.sessions import MAX_SESSIONS_PER_USER, create_session, hash_token
from tests.helpers import auth_headers


def test_telegram_endpoint_removed(client):
    assert client.post("/auth/telegram", json={"init_data": "old"}).status_code == 404
    assert "/auth/telegram" not in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("headers", [
    {"X-Bot-Key": "k" * 40, "X-Telegram-Id": "1"},
    {"X-Dev-Telegram-Id": "1"},
    {"Authorization": "Bearer " + "a" * 43},
])
def test_old_credentials_never_create_accounts(client, session, headers):
    assert client.get("/me", headers=headers).status_code == 401
    assert session.scalar(select(func.count()).select_from(User)) == 0


def test_valid_session_token_requires_cookie(client):
    headers = auth_headers(1)
    token = headers["Cookie"].removeprefix("session=")
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/me", headers=headers).json()["email"] == "user1@example.com"


def test_old_headers_do_not_bypass_cookie_csrf(client):
    headers = auth_headers(1)
    headers.pop("Origin")
    headers.update({"Authorization": "Bearer old", "X-Bot-Key": "k" * 40})
    assert client.post("/categories", json={"name": "A"}, headers=headers).status_code == 403


def test_session_limit_still_discards_oldest_token(client, session):
    headers = auth_headers(1)
    user = session.scalar(select(User).where(User.email == "user1@example.com"))
    for _ in range(MAX_SESSIONS_PER_USER):
        newest, _ = create_session(session, user)
    assert session.scalar(select(func.count()).select_from(AuthSession)) == MAX_SESSIONS_PER_USER
    assert session.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(newest)))
    assert client.get("/me", headers=headers).status_code == 401
    assert client.get("/me", headers={"Cookie": f"session={newest}"}).status_code == 200
