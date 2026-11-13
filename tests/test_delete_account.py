import pytest
from sqlalchemy import func, select

from app.models import (
    AuthSession,
    Category,
    Content,
    EmailVerificationToken,
    PasswordResetToken,
    RateLimitEvent,
    Reminder,
    User,
    UserActivity,
)
from app.passwords import hash_password
from app.routers.email_verification import issue_verification_token
from app.routers.password_reset import issue_reset_token
from app.sessions import create_session
from tests.helpers import ORIGIN, auth_headers as auth

from datetime import datetime, timedelta, timezone

EMAIL = "ivan@example.com"
PASSWORD = "correct horse battery"
WRONG = "wrong wrong wrong"
WITH_ORIGIN = {"Origin": ORIGIN}
URL = "/auth/delete-account"


def register(client, email=EMAIL):
    body = {"email": email, "password": PASSWORD, "consent": True}
    response = client.post("/auth/register", json=body, headers=WITH_ORIGIN)
    assert response.status_code == 201, response.text


def delete_account(client, password=PASSWORD, headers=WITH_ORIGIN, **extra):
    return client.post(URL, json={"password": password, **extra}, headers=headers)


def login(client, password=PASSWORD):
    body = {"email": EMAIL, "password": password}
    return client.post("/auth/login", json=body, headers=WITH_ORIGIN)


def count(session, model, **filters):
    query = select(func.count()).select_from(model)
    for name, value in filters.items():
        query = query.where(getattr(model, name) == value)
    return session.scalar(query)


def test_requires_login(client):
    assert delete_account(client).status_code == 401


def test_success_removes_account_and_session(client, session):
    register(client)
    response = delete_account(client)
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert "max-age=0" in response.headers["set-cookie"].lower()

    assert count(session, User) == 0
    assert client.get("/me").status_code == 401
    assert login(client).status_code == 401


def test_all_user_data_is_removed(client, session):
    register(client)
    user = session.scalar(select(User).where(User.email == EMAIL))
    category = client.post("/categories", json={"name": "Бизнес"}, headers=WITH_ORIGIN).json()
    item = client.post(
        "/contents", json={"note": "текст", "category_id": category["id"]}, headers=WITH_ORIGIN
    ).json()
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    put = client.put(
        f"/contents/{item['id']}/reminder", json={"scheduled_at": when}, headers=WITH_ORIGIN
    )
    assert put.status_code == 200
    issue_reset_token(session, user)
    issue_verification_token(session, user)
    for model in (Category, Content, Reminder, UserActivity, AuthSession,
                  PasswordResetToken, EmailVerificationToken):
        assert count(session, model) >= 1, model.__name__

    assert delete_account(client).status_code == 204
    for model in (User, Category, Content, Reminder, UserActivity, AuthSession,
                  PasswordResetToken, EmailVerificationToken):
        assert count(session, model) == 0, model.__name__


def test_other_users_are_untouched(client, session):
    other = User(email="other@example.com")
    session.add(other)
    session.flush()
    session.add(Category(user_id=other.id, name="Чужая"))
    session.add(Content(user_id=other.id, title="Чужой", note="x"))
    session.flush()
    create_session(session, other)

    register(client)
    assert delete_account(client).status_code == 204

    assert count(session, User) == 1
    assert count(session, Category, user_id=other.id) == 1
    assert count(session, Content, user_id=other.id) == 1
    assert count(session, AuthSession, user_id=other.id) == 1


def test_wrong_password_changes_nothing(client, session):
    register(client)
    response = delete_account(client, password=WRONG)
    assert response.status_code == 400
    assert response.json() == {"detail": "Current password is incorrect"}
    assert count(session, User) == 1
    assert client.get("/me").status_code == 200
    assert login(client).status_code == 200


def test_blocked_after_five_failures(client, session):
    register(client)
    for _ in range(5):
        assert delete_account(client, password=WRONG).status_code == 400
    blocked = delete_account(client, password=WRONG)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert delete_account(client).status_code == 429  # верный пароль тоже не пускает
    assert count(session, User) == 1
    assert count(session, RateLimitEvent, bucket="password_user") == 5


def test_success_resets_the_counter(client, session):
    register(client)
    for _ in range(4):
        assert delete_account(client, password=WRONG).status_code == 400
    assert delete_account(client).status_code == 204
    assert count(session, RateLimitEvent, bucket="password_user") == 0


def test_invalid_requests_are_not_counted_and_delete_nothing(client, session):
    register(client)
    assert delete_account(client, password="").status_code == 422
    assert delete_account(client, password="x" * 129).status_code == 422
    assert delete_account(client, extra_field=1).status_code == 422
    assert client.post(URL, json={}, headers=WITH_ORIGIN).status_code == 422
    assert count(session, RateLimitEvent, bucket="password_user") == 0
    assert count(session, User) == 1


def test_cookie_request_needs_origin(client, session):
    register(client)
    assert delete_account(client, headers={}).status_code == 403
    assert delete_account(client, headers={"Origin": "http://evil.example"}).status_code == 403
    assert count(session, User) == 1


def test_account_without_password_cannot_be_deleted(client, session):
    response = delete_account(client, headers=auth(1))
    assert response.status_code == 400
    assert response.json() == {"detail": "Account has no password"}
    assert count(session, User) == 1


def test_bearer_session_can_delete(client, session):
    user = User(email=EMAIL, password_hash=hash_password(PASSWORD))
    session.add(user)
    session.flush()
    token, _ = create_session(session, user)
    headers = {"Authorization": f"Bearer {token}"}

    assert delete_account(client, headers=headers).status_code == 204
    assert count(session, User) == 0
    assert client.get("/me", headers=headers).status_code == 401


def test_the_same_email_can_register_again(client, session):
    register(client)
    assert delete_account(client).status_code == 204
    register(client)
    assert count(session, User) == 1