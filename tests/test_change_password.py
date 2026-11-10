import pytest
from sqlalchemy import func, select

from app.models import AuthSession, PasswordResetToken, RateLimitEvent, User
from app.passwords import verify_password
from app.routers.password_reset import issue_reset_token
from app.sessions import create_session, hash_token
from tests.helpers import ORIGIN, auth_headers as auth

EMAIL = "ivan@example.com"
PASSWORD = "correct horse battery"
NEW_PASSWORD = "brand new horse staple"
WRONG = "wrong wrong wrong"
WITH_ORIGIN = {"Origin": ORIGIN}


def register(client):
    body = {"email": EMAIL, "password": PASSWORD, "consent": True}
    response = client.post("/auth/register", json=body, headers=WITH_ORIGIN)
    assert response.status_code == 201, response.text


def change(client, current=PASSWORD, new=NEW_PASSWORD, headers=WITH_ORIGIN, **extra):
    body = {"current_password": current, "new_password": new, **extra}
    return client.post("/auth/change-password", json=body, headers=headers)


def login(client, password):
    body = {"email": EMAIL, "password": password}
    return client.post("/auth/login", json=body, headers=WITH_ORIGIN)


def count(session, model, **filters):
    query = select(func.count()).select_from(model)
    for name, value in filters.items():
        query = query.where(getattr(model, name) == value)
    return session.scalar(query)


def test_requires_login(client):
    assert change(client).status_code == 401


def test_success_changes_password_and_keeps_current_session(client, session):
    register(client)
    response = change(client)
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/me").status_code == 200  # текущая сессия жива

    user = session.scalar(select(User).where(User.email == EMAIL))
    session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert user.password_hash.startswith("$argon2id$")

    assert login(client, PASSWORD).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200


def test_other_sessions_are_closed_current_one_stays(client, session):
    register(client)
    user = session.scalar(select(User).where(User.email == EMAIL))
    create_session(session, user)  # «другое устройство»
    other_user = User(email="other@example.com")
    session.add(other_user)
    session.flush()
    create_session(session, other_user)  # чужая сессия не должна пострадать
    assert count(session, AuthSession) == 3

    assert change(client).status_code == 204

    assert count(session, AuthSession, user_id=user.id) == 1
    assert count(session, AuthSession, user_id=other_user.id) == 1
    kept = session.scalar(select(AuthSession.token_hash).where(AuthSession.user_id == user.id))
    assert kept == hash_token(client.cookies.get("session"))


def test_reset_links_issued_before_are_cancelled(client, session):
    register(client)
    user = session.scalar(select(User).where(User.email == EMAIL))
    issue_reset_token(session, user)
    assert count(session, PasswordResetToken) == 1
    assert change(client).status_code == 204
    assert count(session, PasswordResetToken) == 0


def test_wrong_current_password_changes_nothing(client, session):
    register(client)
    sessions_before = count(session, AuthSession)
    response = change(client, current=WRONG)
    assert response.status_code == 400
    assert response.json() == {"detail": "Current password is incorrect"}
    assert count(session, AuthSession) == sessions_before
    assert login(client, PASSWORD).status_code == 200
    assert login(client, NEW_PASSWORD).status_code == 401


def test_blocked_after_five_failures(client, session):
    register(client)
    for _ in range(5):
        assert change(client, current=WRONG).status_code == 400
    blocked = change(client, current=WRONG)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert change(client).status_code == 429  # верный пароль тоже не пускает
    assert count(session, RateLimitEvent, bucket="password_user") == 5


def test_success_resets_the_counter(client, session):
    register(client)
    for _ in range(4):
        assert change(client, current=WRONG).status_code == 400
    assert change(client).status_code == 204
    assert count(session, RateLimitEvent, bucket="password_user") == 0


def test_invalid_requests_are_not_counted(client, session):
    register(client)
    assert change(client, new="short").status_code == 422
    assert change(client, new=PASSWORD).status_code == 422  # совпадает с текущим
    assert change(client, new="x" * 129).status_code == 422
    assert change(client, extra_field=1).status_code == 422
    assert count(session, RateLimitEvent, bucket="password_user") == 0
    assert login(client, PASSWORD).status_code == 200


def test_cookie_request_needs_origin(client):
    register(client)
    assert change(client, headers={}).status_code == 403
    assert change(client, headers={"Origin": "http://evil.example"}).status_code == 403
    assert login(client, PASSWORD).status_code == 200  # пароль не изменился


def test_account_without_password_cannot_change_it(client):
    response = change(client, headers=auth(1))
    assert response.status_code == 400
    assert response.json() == {"detail": "Account has no password"}


def test_bearer_session_is_kept_too(client, session):
    user = User(email=EMAIL)
    from app.passwords import hash_password

    user.password_hash = hash_password(PASSWORD)
    session.add(user)
    session.flush()
    token, _ = create_session(session, user)
    create_session(session, user)
    headers = {"Authorization": f"Bearer {token}"}

    assert change(client, headers=headers).status_code == 204
    assert client.get("/me", headers=headers).status_code == 200
    assert count(session, AuthSession, user_id=user.id) == 1