from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select, text

import app.routers.auth as auth_module
from app.config import settings
from app.models import AuthSession, User
from app.passwords import hash_password, needs_rehash, verify_password
from app.sessions import SESSION_ABSOLUTE, SESSION_IDLE
from tests.helpers import ORIGIN, auth_headers

EMAIL = "ivan@example.com"
PASSWORD = "correct horse battery"
WITH_ORIGIN = {"Origin": ORIGIN}


def post(client, path, json=None, headers=WITH_ORIGIN):
    return client.post(path, json=json, headers=headers)


def register(client, email=EMAIL, password=PASSWORD, headers=WITH_ORIGIN):
    body = {"email": email, "password": password, "consent": True}
    return post(client, "/auth/register", body, headers)


def login(client, email=EMAIL, password=PASSWORD, headers=WITH_ORIGIN):
    return post(client, "/auth/login", {"email": email, "password": password}, headers)


def make_user(session, email=EMAIL, password=PASSWORD, **fields):
    user = User(email=email, password_hash=hash_password(password), **fields)
    session.add(user)
    session.flush()
    return user


def count_sessions(session):
    return session.scalar(select(func.count()).select_from(AuthSession))


def cookie_attributes(response):
    parts = response.headers["set-cookie"].split(";")
    return [part.strip().lower() for part in parts[1:]]


# ---------- cookie ----------


def test_register_starts_session(client):
    assert register(client).status_code == 201
    assert client.cookies.get("session") is not None
    assert client.get("/me").json()["email"] == EMAIL


def test_cookie_attributes_in_development(client):
    attrs = cookie_attributes(register(client))
    assert "httponly" in attrs
    assert "samesite=lax" in attrs
    assert "path=/" in attrs
    assert f"max-age={int(SESSION_ABSOLUTE.total_seconds())}" in attrs
    assert "secure" not in attrs


def test_cookie_in_secure_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = register(client)
    assert response.headers["set-cookie"].startswith("__Host-session=")
    attrs = cookie_attributes(response)
    assert "secure" in attrs and "httponly" in attrs and "path=/" in attrs
    assert not any(attr.startswith("domain") for attr in attrs)


# ---------- вход ----------


def test_login_success(client, session):
    make_user(session)
    response = login(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["email"] == EMAIL
    assert "password_hash" not in body
    assert client.get("/me").status_code == 200


def test_login_email_is_case_insensitive(client, session):
    make_user(session)
    assert login(client, email="  IVAN@Example.com ").status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(client, session):
    make_user(session)
    wrong = login(client, password="wrong wrong wrong")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}
    assert "set-cookie" not in wrong.headers
    assert "set-cookie" not in unknown.headers


def test_malformed_email_gives_401_not_422(client):
    assert login(client, email="plain").status_code == 401


def test_user_without_password_cannot_log_in(client, session):
    session.add(User(email=EMAIL))
    session.flush()
    assert login(client).status_code == 401


def test_dummy_verification_only_for_unknown_accounts(client, session, monkeypatch):
    calls = []
    monkeypatch.setattr(auth_module, "verify_dummy", lambda password: calls.append(1))
    make_user(session)
    login(client, password="wrong wrong wrong")
    assert calls == []
    login(client, email="nobody@example.com")
    assert calls == [1]


def test_login_validation(client):
    assert post(client, "/auth/login", {"email": EMAIL, "password": ""}).status_code == 422
    assert post(client, "/auth/login", {"email": EMAIL}).status_code == 422
    body = {"email": EMAIL, "password": PASSWORD, "remember": True}
    assert post(client, "/auth/login", body).status_code == 422


def test_login_replaces_previous_session(client, session):
    make_user(session)
    assert login(client).status_code == 200
    old = client.cookies.get("session")
    assert count_sessions(session) == 1

    assert login(client).status_code == 200
    assert client.cookies.get("session") != old
    assert count_sessions(session) == 1

    client.cookies.clear()
    response = client.get("/me", headers={"Cookie": f"session={old}"})
    assert response.status_code == 401


def test_weak_hash_is_upgraded_on_login(client, session):
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    user = User(email=EMAIL, password_hash=weak)
    session.add(user)
    session.flush()
    assert login(client).status_code == 200
    session.refresh(user)
    assert user.password_hash != weak
    assert not needs_rehash(user.password_hash)
    assert verify_password(PASSWORD, user.password_hash)


# ---------- выход ----------


def test_logout_deletes_session_and_cookie(client, session):
    make_user(session)
    login(client)
    assert count_sessions(session) == 1

    response = post(client, "/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in cookie_attributes(response)
    assert count_sessions(session) == 0
    assert client.get("/me").status_code == 401


def test_logout_without_session_is_fine(client):
    assert post(client, "/auth/logout").status_code == 204
    garbage = {**WITH_ORIGIN, "Cookie": "session=" + "A" * 43}
    assert post(client, "/auth/logout", headers=garbage).status_code == 204


# ---------- проверка Origin ----------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "http://evil.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
def test_site_auth_endpoints_reject_foreign_requests(client, session, headers):
    make_user(session)
    body = {"email": EMAIL, "password": PASSWORD}
    assert client.post("/auth/login", json=body, headers=headers).status_code == 403
    assert client.post("/auth/logout", headers=headers).status_code == 403
    register_body = {"email": "new@example.com", "password": PASSWORD, "consent": True}
    assert client.post("/auth/register", json=register_body, headers=headers).status_code == 403


def test_sec_fetch_site_is_used_when_origin_is_missing(client, session):
    make_user(session)
    body = {"email": EMAIL, "password": PASSWORD}
    headers = {"Sec-Fetch-Site": "same-origin"}
    assert client.post("/auth/login", json=body, headers=headers).status_code == 200


def test_cookie_requests_are_checked_for_origin(client, session):
    make_user(session)
    login(client)
    body = {"name": "Бизнес"}

    assert client.post("/categories", json=body).status_code == 403
    evil = {"Origin": "http://evil.example"}
    assert client.post("/categories", json=body, headers=evil).status_code == 403
    created = client.post("/categories", json=body, headers=WITH_ORIGIN)
    assert created.status_code == 201

    category_id = created.json()["id"]
    assert client.delete(f"/categories/{category_id}").status_code == 403
    assert client.get("/categories").status_code == 200  # чтение без Origin


def test_bearer_requests_need_no_origin(client):
    headers = auth_headers(1)
    assert client.post("/categories", json={"name": "A"}, headers=headers).status_code == 201


# ---------- один способ входа за запрос ----------


def test_cookie_with_bearer_is_rejected(client, session):
    make_user(session)
    login(client)
    assert client.get("/me", headers=auth_headers(5)).status_code == 401


def test_cookie_with_bot_key_is_rejected(client, session):
    make_user(session)
    login(client)
    headers = {"X-Bot-Key": "k" * 40, "X-Telegram-Id": "1"}
    assert client.get("/me", headers=headers).status_code == 401


@pytest.mark.parametrize("value", ["A" * 43, "short"])
def test_bad_cookie_rejected(client, value):
    assert client.get("/me", headers={"Cookie": f"session={value}"}).status_code == 401


def test_expired_cookie_session_rejected(client, session):
    make_user(session)
    login(client)
    session.execute(
        text(
            "UPDATE auth_sessions SET created_at = now() - interval '3 days', "
            "expires_at = now() - interval '1 day'"
        )
    )
    assert client.get("/me").status_code == 401


# ---------- продление сессии ----------


def set_times(session, created_hours_ago, expires_in_hours):
    # Числа задаются в самом тесте, не пользователем: подстановка в SQL безопасна
    session.execute(
        text(
            f"UPDATE auth_sessions SET created_at = now() - interval '{created_hours_ago} hours', "
            f"expires_at = now() + interval '{expires_in_hours} hours'"
        )
    )


def stored_expiry(session):
    return session.scalar(select(AuthSession.expires_at))


def test_session_is_extended_when_due(client, session):
    make_user(session)
    login(client)
    set_times(session, created_hours_ago=240, expires_in_hours=24)

    assert client.get("/me").status_code == 200
    remaining = stored_expiry(session) - datetime.now(timezone.utc)
    assert timedelta(days=13, hours=23) < remaining <= SESSION_IDLE


def test_recently_extended_session_is_not_written_again(client, session):
    make_user(session)
    login(client)
    set_times(session, created_hours_ago=240, expires_in_hours=335)
    before = stored_expiry(session)

    assert client.get("/me").status_code == 200
    assert stored_expiry(session) == before


def test_extension_never_passes_the_absolute_limit(client, session):
    make_user(session)
    login(client)
    set_times(session, created_hours_ago=1320, expires_in_hours=24)

    assert client.get("/me").status_code == 200
    row = session.execute(select(AuthSession.created_at, AuthSession.expires_at)).one()
    assert row.expires_at == row.created_at + SESSION_ABSOLUTE