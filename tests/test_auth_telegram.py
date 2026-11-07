import time

import pytest
from sqlalchemy import func, select, text

from app.config import settings
from app.models import AuthSession, User
from app.sessions import MAX_SESSIONS_PER_USER, hash_token
from tests.helpers import USER, build_init_data

TOKEN = "123456:TEST-token-not-real"  # выдуманный токен


@pytest.fixture(autouse=True)
def bot_token(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", TOKEN)


def login(client, user=USER, **kwargs):
    init_data = build_init_data(TOKEN, user=user, **kwargs)
    return client.post("/auth/telegram", json={"init_data": init_data})


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_login_returns_token_and_user(client, session):
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["token"]) >= 40
    assert body["user"]["telegram_id"] == 42
    assert body["user"]["username"] == "ivan_1"
    assert "expires_at" in body
    assert response.headers["cache-control"] == "no-store"

    rows = session.scalars(select(AuthSession)).all()
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(body["token"])
    assert rows[0].token_hash != body["token"]  # в БД лежит хэш, не токен


def test_second_login_reuses_user_and_issues_new_token(client, session):
    first = login(client).json()
    second = login(client).json()
    assert first["user"]["id"] == second["user"]["id"]
    assert first["token"] != second["token"]
    assert count(session, User) == 1
    assert count(session, AuthSession) == 2


def test_username_updated_and_cleared(client):
    login(client)
    renamed = login(client, user={**USER, "username": "new_name"}).json()
    assert renamed["user"]["username"] == "new_name"
    cleared = login(client, user={"id": 42, "first_name": "Иван"}).json()
    assert cleared["user"]["username"] is None


def test_hash_token_is_64_hex_and_stable():
    value = hash_token("abc")
    assert len(value) == 64
    assert value == hash_token("abc")
    assert value != hash_token("abd")


# ---------- отказы ----------


def assert_rejected(client, session, response):
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert count(session, User) == 0
    assert count(session, AuthSession) == 0


def test_wrong_signature_rejected(client, session):
    init_data = build_init_data("999:OTHER-token", user=USER)
    response = client.post("/auth/telegram", json={"init_data": init_data})
    assert_rejected(client, session, response)


def test_expired_init_data_rejected(client, session):
    response = login(client, auth_date=int(time.time()) - 7200)
    assert_rejected(client, session, response)


def test_garbage_init_data_rejected(client, session):
    response = client.post("/auth/telegram", json={"init_data": "hello"})
    assert_rejected(client, session, response)


def test_login_unavailable_without_bot_token(client, session, monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "")
    assert login(client).status_code == 503
    assert count(session, AuthSession) == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"init_data": ""},
        {"init_data": "x" * 9000},
        {"init_data": 5},
        {"init_data": "x", "foo": 1},
    ],
)
def test_bad_request_body_rejected(client, body):
    assert client.post("/auth/telegram", json=body).status_code == 422


# ---------- управление сессиями ----------


def test_session_cap_keeps_newest(client, session):
    last = None
    for _ in range(MAX_SESSIONS_PER_USER + 2):
        last = login(client).json()["token"]
    assert count(session, AuthSession) == MAX_SESSIONS_PER_USER
    newest = session.scalar(
        select(AuthSession.id).where(AuthSession.token_hash == hash_token(last))
    )
    assert newest is not None


def add_expired(session, user_id, token_hash):
    session.add(
        AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            created_at=text("now() - interval '3 days'"),
            expires_at=text("now() - interval '2 days'"),
        )
    )
    session.flush()


def test_login_removes_own_expired_sessions_only(client, session):
    mine = login(client).json()["user"]["id"]
    other = login(client, user={"id": 43, "first_name": "Анна"}).json()["user"]["id"]
    add_expired(session, mine, "c" * 64)
    add_expired(session, other, "d" * 64)

    login(client)  # вход пользователя 42

    hashes = set(session.scalars(select(AuthSession.token_hash)).all())
    assert "c" * 64 not in hashes  # своя просроченная удалена
    assert "d" * 64 in hashes  # чужую не трогаем