from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

import app.routers.password_reset as reset_module
from app.models import AuthSession, PasswordResetToken, User
from app.passwords import hash_password
from app.ratelimit import Rule
from app.sessions import create_session, hash_token
from tests.helpers import ORIGIN

EMAIL = "ivan@example.com"
PASSWORD = "correct horse battery"
NEW_PASSWORD = "brand new horse staple"
WITH_ORIGIN = {"Origin": ORIGIN}
NEUTRAL = {"detail": "If the address is registered, a reset link has been sent."}
INVALID = {"detail": "Invalid or expired token"}


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(
        reset_module, "send_password_reset", lambda to, link: sent.append((to, link))
    )
    return sent


def make_user(session, email=EMAIL, password=PASSWORD, **fields):
    user = User(email=email, password_hash=hash_password(password), **fields)
    session.add(user)
    session.flush()
    return user


def request_reset(client, email=EMAIL, headers=WITH_ORIGIN):
    return client.post("/auth/password-reset/request", json={"email": email}, headers=headers)


def confirm(client, token, password=NEW_PASSWORD, headers=WITH_ORIGIN):
    body = {"token": token, "password": password}
    return client.post("/auth/password-reset/confirm", json=body, headers=headers)


def login(client, email=EMAIL, password=PASSWORD):
    body = {"email": email, "password": password}
    return client.post("/auth/login", json=body, headers=WITH_ORIGIN)


def token_from(link):
    return link.split("#token=", 1)[1]


def issue(client, outbox, email=EMAIL):
    assert request_reset(client, email).status_code == 202
    return token_from(outbox[-1][1])


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


# ---------- запрос ----------


def test_request_sends_link_for_known_account(client, session, outbox):
    make_user(session)
    response = request_reset(client)
    assert response.status_code == 202
    assert response.json() == NEUTRAL
    assert response.headers["cache-control"] == "no-store"

    assert len(outbox) == 1
    to, link = outbox[0]
    assert to == EMAIL
    assert link.startswith(f"{ORIGIN}/app/reset.html#token=")
    token = token_from(link)

    row = session.scalars(select(PasswordResetToken)).one()
    assert row.token_hash == hash_token(token)
    assert row.token_hash != token
    remaining = row.expires_at - datetime.now(timezone.utc)
    assert timedelta(minutes=59) < remaining <= timedelta(hours=1)


def test_unknown_account_gets_the_same_answer_and_no_mail(client, session, outbox):
    make_user(session)
    known = request_reset(client)
    unknown = request_reset(client, email="nobody@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert known.headers["cache-control"] == unknown.headers["cache-control"]
    assert len(outbox) == 1
    assert count(session, PasswordResetToken) == 1


def test_request_normalizes_email(client, session, outbox):
    make_user(session)
    assert request_reset(client, email="  IVAN@Example.com ").status_code == 202
    assert outbox[0][0] == EMAIL


def test_new_request_invalidates_previous_token(client, session, outbox):
    make_user(session)
    first = issue(client, outbox)
    second = issue(client, outbox)
    assert count(session, PasswordResetToken) == 1
    assert confirm(client, first).status_code == 400
    assert confirm(client, second).status_code == 204


def test_expired_tokens_of_others_are_cleaned_up(client, session, outbox):
    make_user(session, email="other@example.com")
    make_user(session)
    issue(client, outbox, email="other@example.com")
    session.execute(
        text(
            "UPDATE password_reset_tokens SET created_at = now() - interval '2 hours', "
            "expires_at = now() - interval '1 hour'"
        )
    )
    issue(client, outbox)
    assert count(session, PasswordResetToken) == 1


def test_request_validation_and_origin(client, session, outbox):
    make_user(session)
    assert request_reset(client, email="plain").status_code == 422
    assert request_reset(client, headers={}).status_code == 403
    assert request_reset(client, headers={"Origin": "http://evil.example"}).status_code == 403
    extra = {"email": EMAIL, "admin": True}
    assert client.post("/auth/password-reset/request", json=extra, headers=WITH_ORIGIN).status_code == 422
    assert outbox == []


# ---------- ограничение частоты ----------


def test_request_limited_per_email(client, session, outbox):
    make_user(session)
    assert [request_reset(client).status_code for _ in range(3)] == [202, 202, 202]
    blocked = request_reset(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert len(outbox) == 3


def test_request_limited_per_ip_for_any_address(client, session, outbox, monkeypatch):
    monkeypatch.setattr(reset_module, "RESET_IP", Rule("reset_ip", 2, timedelta(hours=1)))
    make_user(session)
    assert request_reset(client).status_code == 202
    assert request_reset(client, email="nobody@example.com").status_code == 202
    assert request_reset(client, email="third@example.com").status_code == 429
    assert len(outbox) == 1


# ---------- подтверждение ----------


def test_confirm_changes_password_and_verifies_email(client, session, outbox):
    user = make_user(session)
    token = issue(client, outbox)

    response = confirm(client, token)
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert count(session, PasswordResetToken) == 0

    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200
    session.refresh(user)
    assert user.email_verified_at is not None


def test_confirm_keeps_existing_verification_time(client, session, outbox):
    verified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    user = make_user(session, email_verified_at=verified)
    assert confirm(client, issue(client, outbox)).status_code == 204
    session.refresh(user)
    assert user.email_verified_at == verified


def test_confirm_closes_all_sessions_of_that_user_only(client, session, outbox):
    user = make_user(session)
    other = make_user(session, email="other@example.com")
    login(client)
    old_cookie = client.cookies.get("session")
    bearer, _ = create_session(session, user)
    create_session(session, other)
    assert count(session, AuthSession) == 3

    assert confirm(client, issue(client, outbox)).status_code == 204
    assert count(session, AuthSession) == 1  # осталась только сессия другого

    client.cookies.clear()
    assert client.get("/me", headers={"Cookie": f"session={old_cookie}"}).status_code == 401
    assert client.get("/me", headers={"Authorization": f"Bearer {bearer}"}).status_code == 401


def test_token_is_single_use(client, session, outbox):
    make_user(session)
    token = issue(client, outbox)
    assert confirm(client, token).status_code == 204
    again = confirm(client, token, password="another new password")
    assert again.status_code == 400
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_expired_token_rejected(client, session, outbox):
    make_user(session)
    token = issue(client, outbox)
    session.execute(
        text(
            "UPDATE password_reset_tokens SET created_at = now() - interval '2 hours', "
            "expires_at = now() - interval '1 hour'"
        )
    )
    response = confirm(client, token)
    assert response.status_code == 400
    assert response.json() == INVALID
    assert login(client).status_code == 200  # прежний пароль не тронут


@pytest.mark.parametrize("token", ["A" * 43, "short", "bad chars!! bad chars!! bad"])
def test_unknown_or_malformed_tokens_look_the_same(client, session, token):
    make_user(session)
    response = confirm(client, token)
    assert response.status_code == 400
    assert response.json() == INVALID


def test_weak_password_does_not_consume_the_token(client, session, outbox):
    make_user(session)
    token = issue(client, outbox)
    assert confirm(client, token, password="short").status_code == 422
    assert confirm(client, token).status_code == 204


def test_confirm_requires_origin_and_rejects_extra_fields(client, session, outbox):
    make_user(session)
    token = issue(client, outbox)
    assert confirm(client, token, headers={}).status_code == 403
    body = {"token": token, "password": NEW_PASSWORD, "email": EMAIL}
    url = "/auth/password-reset/confirm"
    assert client.post(url, json=body, headers=WITH_ORIGIN).status_code == 422
    assert confirm(client, token).status_code == 204  # токен не потрачен