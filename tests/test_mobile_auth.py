from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.cookies import cookie_name
from app.models import AuthSession, User
from app.sessions import MAX_SESSIONS_PER_USER, SESSION_ABSOLUTE, hash_token
from tests.helpers import ORIGIN

DATA = {"email": "mobile@example.com", "password": "mobile-password-42", "consent": True}


def register(client):
    response = client.post("/mobile/auth/register", json=DATA)
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_native_registration_session_and_web_compatibility(client, session):
    data = register(client)
    token = data["token"]
    assert data["token_type"] == "Bearer"
    assert data["user"]["email"] == DATA["email"]
    row = session.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    assert row.client_type == "mobile" and token != row.token_hash
    assert client.get("/me", headers=bearer(token)).json()["id"] == data["user"]["id"]
    response = client.get("/mobile/auth/session", headers=bearer(token))
    assert response.status_code == 200 and "token" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert client.get("/me", headers={"Cookie": f"{cookie_name()}={token}"}).status_code == 401
    web = client.post("/auth/login", json={k: DATA[k] for k in ("email", "password")}, headers={"Origin": ORIGIN})
    assert web.status_code == 200
    web_token = client.cookies[cookie_name()]
    client.cookies.clear()
    assert client.get("/me", headers=bearer(web_token)).status_code == 401
    assert client.get("/me", headers={"Cookie": f"{cookie_name()}={web_token}"}).status_code == 200


@pytest.mark.parametrize("extra", [
    {"Origin": ORIGIN}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "same-origin"},
    {"Cookie": "session=other"}, {"Authorization": "Bearer other"},
])
def test_native_signup_refuses_browser_or_existing_credentials(client, session, extra):
    assert client.post("/mobile/auth/register", json=DATA, headers=extra).status_code in (401, 403)
    assert session.scalar(select(User).where(User.email == DATA["email"])) is None


@pytest.mark.parametrize("authorization", ["", "Basic abc", "Bearer", "Bearer abc extra", "Bearer ", "Bearer old"])
def test_mixed_credentials_do_not_fall_back_to_cookie(client, authorization):
    client.post("/auth/register", json=DATA, headers={"Origin": ORIGIN})
    assert client.get("/me", headers={"Authorization": authorization}).status_code == 401


def test_native_login_no_cookie_no_store_and_logout(client, session):
    first = register(client)
    response = client.post("/mobile/auth/login", json={k: DATA[k] for k in ("email", "password")})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    second = response.json()
    assert second["token"] != first["token"]
    response = client.post("/mobile/auth/logout", headers=bearer(second["token"]))
    assert response.status_code == 204 and "set-cookie" not in response.headers
    assert client.get("/me", headers=bearer(second["token"])).status_code == 401
    assert client.get("/me", headers=bearer(first["token"])).status_code == 200


def test_native_change_password_keeps_current_and_revokes_other_transports(client):
    data = register(client)
    client.post("/auth/login", json={k: DATA[k] for k in ("email", "password")}, headers={"Origin": ORIGIN})
    web_token = client.cookies[cookie_name()]
    client.cookies.clear()
    token = data["token"]
    changed = client.post("/auth/change-password", headers=bearer(token), json={"current_password": DATA["password"], "new_password": "new-mobile-password"})
    assert changed.status_code == 204
    assert client.get("/me", headers=bearer(token)).status_code == 200
    assert client.get("/me", headers={"Cookie": f"{cookie_name()}={web_token}"}).status_code == 401


def test_reset_revokes_all_transports_and_verifies_email(client, session):
    from app.routers.password_reset import issue_reset_token
    data = register(client)
    user = session.get(User, data["user"]["id"])
    reset_token = issue_reset_token(session, user)
    response = client.post("/mobile/auth/password-reset/confirm", json={"token": reset_token, "password": "changed-password-42"})
    assert response.status_code == 204 and "set-cookie" not in response.headers
    assert client.get("/me", headers=bearer(data["token"])).status_code == 401
    assert client.post("/mobile/auth/password-reset/confirm", json={"token": reset_token, "password": "changed-password-42"}).status_code == 400
    assert client.post("/mobile/auth/login", json={"email": DATA["email"], "password": "changed-password-42"}).status_code == 200


def test_shared_verification_without_session_and_one_time_use(client, session):
    from app.routers.email_verification import issue_verification_token
    data = register(client)
    token = issue_verification_token(session, session.get(User, data["user"]["id"]))
    response = client.post("/mobile/auth/email-verification/confirm", json={"token": token})
    assert response.status_code == 204 and "set-cookie" not in response.headers
    assert client.get("/me", headers=bearer(data["token"])).json()["email_verified_at"] is not None
    assert client.post("/mobile/auth/email-verification/confirm", json={"token": token}).status_code == 400


@pytest.mark.parametrize("expired", ["idle", "absolute"])
def test_expiry_and_absolute_limit(client, session, expired):
    data = register(client)
    row = session.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(data["token"])))
    now = datetime.now(timezone.utc)
    row.created_at = now - (SESSION_ABSOLUTE + timedelta(days=1) if expired == "absolute" else timedelta(days=15))
    row.expires_at = now + timedelta(days=1) if expired == "absolute" else now - timedelta(seconds=1)
    session.commit()
    assert client.get("/me", headers=bearer(data["token"])).status_code == 401


def test_web_and_mobile_use_one_session_limit(client, session):
    first = register(client)
    for _ in range(MAX_SESSIONS_PER_USER):
        assert client.post("/mobile/auth/login", json={k: DATA[k] for k in ("email", "password")}).status_code == 200
    rows = session.scalars(select(AuthSession)).all()
    assert len(rows) == MAX_SESSIONS_PER_USER
    assert client.get("/me", headers=bearer(first["token"])).status_code == 401


def test_validation_and_failures_never_echo_secrets_and_are_not_cached(client):
    secret = "not-a-valid-secret"
    response = client.post("/mobile/auth/register", json={**DATA, "consent": False, "password": secret})
    assert response.status_code == 422 and secret not in response.text
    assert response.headers["cache-control"] == "no-store"
    response = client.post("/mobile/auth/login", json={"email": "unknown@example.com", "password": secret})
    assert response.status_code == 401 and secret not in response.text
    assert response.headers["cache-control"] == "no-store"
