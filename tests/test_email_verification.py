from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

import app.routers.email_verification as verify_module
from app.models import EmailVerificationToken, User
from app.ratelimit import Rule
from app.sessions import hash_token
from tests.helpers import ORIGIN, auth_headers as auth

EMAIL = "ivan@example.com"
PASSWORD = "correct horse battery"
WITH_ORIGIN = {"Origin": ORIGIN}
INVALID = {"detail": "Invalid or expired token"}


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(
        verify_module, "send_email_verification", lambda to, link: sent.append((to, link))
    )
    return sent


def register(client, email=EMAIL):
    body = {"email": email, "password": PASSWORD, "consent": True}
    response = client.post("/auth/register", json=body, headers=WITH_ORIGIN)
    assert response.status_code == 201, response.text
    return response


def request_link(client, headers=WITH_ORIGIN):
    return client.post("/auth/email-verification/request", headers=headers)


def confirm(client, token, headers=WITH_ORIGIN):
    return client.post(
        "/auth/email-verification/confirm", json={"token": token}, headers=headers
    )


def token_from(link):
    return link.split("#token=", 1)[1]


def issue(client, outbox):
    assert request_link(client).status_code == 202
    return token_from(outbox[-1][1])


def count(session):
    return session.scalar(select(func.count()).select_from(EmailVerificationToken))


def expire_all_tokens(session):
    session.execute(
        text(
            "UPDATE email_verification_tokens SET created_at = now() - interval '2 days', "
            "expires_at = now() - interval '1 day'"
        )
    )


# ---------- запрос ----------


def test_request_requires_login(client, outbox):
    assert client.post("/auth/email-verification/request").status_code == 401
    assert outbox == []


def test_request_sends_link_and_stores_hash(client, session, outbox):
    register(client)
    response = request_link(client)
    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store"

    assert len(outbox) == 1
    to, link = outbox[0]
    assert to == EMAIL
    assert link.startswith(f"{ORIGIN}/app/verify.html#token=")
    token = token_from(link)

    row = session.scalars(select(EmailVerificationToken)).one()
    assert row.token_hash == hash_token(token)
    assert row.token_hash != token
    remaining = row.expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=23, minutes=59) < remaining <= timedelta(hours=24)


def test_cookie_request_needs_origin(client, outbox):
    register(client)
    assert request_link(client, headers={}).status_code == 403
    assert request_link(client, headers={"Origin": "http://evil.example"}).status_code == 403
    assert outbox == []


def test_new_request_invalidates_previous_token(client, session, outbox):
    register(client)
    first = issue(client, outbox)
    second = issue(client, outbox)
    assert count(session) == 1
    assert confirm(client, first).status_code == 400
    assert confirm(client, second).status_code == 204


def test_account_without_email_cannot_request(client, outbox):
    response = client.post("/auth/email-verification/request", headers=auth(1))
    assert response.status_code == 400
    assert outbox == []


def test_already_verified_gets_conflict_and_no_mail(client, session, outbox):
    register(client)
    user = session.scalar(select(User).where(User.email == EMAIL))
    user.email_verified_at = datetime.now(timezone.utc)
    session.flush()
    assert request_link(client).status_code == 409
    assert outbox == []


def test_expired_tokens_of_others_are_cleaned_up(client, session, outbox):
    register(client, "first@example.com")
    issue(client, outbox)
    expire_all_tokens(session)
    register(client, "second@example.com")
    issue(client, outbox)
    assert count(session) == 1


# ---------- ограничение частоты ----------


def test_request_limited_per_user(client, outbox):
    register(client)
    assert [request_link(client).status_code for _ in range(3)] == [202, 202, 202]
    blocked = request_link(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert len(outbox) == 3


def test_request_limited_per_ip(client, outbox, monkeypatch):
    monkeypatch.setattr(verify_module, "VERIFY_IP", Rule("verify_ip", 2, timedelta(hours=1)))
    codes = []
    for email in ("a@example.com", "b@example.com", "c@example.com"):
        register(client, email)
        codes.append(request_link(client).status_code)
    assert codes == [202, 202, 429]
    assert len(outbox) == 2


# ---------- подтверждение ----------


def test_confirm_sets_verification_time(client, session, outbox):
    register(client)
    assert client.get("/me").json()["email_verified_at"] is None
    token = issue(client, outbox)

    response = confirm(client, token)
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert count(session) == 0
    assert client.get("/me").json()["email_verified_at"] is not None


def test_confirm_works_without_a_session(client, outbox):
    register(client)
    token = issue(client, outbox)
    client.cookies.clear()
    assert confirm(client, token).status_code == 204
    login = client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=WITH_ORIGIN
    )
    assert login.status_code == 200
    assert client.get("/me").json()["email_verified_at"] is not None


def test_token_is_single_use(client, outbox):
    register(client)
    token = issue(client, outbox)
    assert confirm(client, token).status_code == 204
    again = confirm(client, token)
    assert again.status_code == 400
    assert again.json() == INVALID


def test_expired_token_rejected(client, session, outbox):
    register(client)
    token = issue(client, outbox)
    expire_all_tokens(session)
    response = confirm(client, token)
    assert response.status_code == 400
    assert response.json() == INVALID
    assert client.get("/me").json()["email_verified_at"] is None


@pytest.mark.parametrize("token", ["A" * 43, "short", "bad chars!! bad chars!! bad"])
def test_unknown_or_malformed_tokens_look_the_same(client, token):
    response = confirm(client, token)
    assert response.status_code == 400
    assert response.json() == INVALID


def test_confirm_requires_origin_and_keeps_the_token(client, outbox):
    register(client)
    token = issue(client, outbox)
    assert confirm(client, token, headers={}).status_code == 403
    assert confirm(client, token, headers={"Origin": "http://evil.example"}).status_code == 403
    assert confirm(client, token).status_code == 204


def test_confirm_rejects_extra_fields_without_spending_the_token(client, outbox):
    register(client)
    token = issue(client, outbox)
    body = {"token": token, "email": EMAIL}
    url = "/auth/email-verification/confirm"
    assert client.post(url, json=body, headers=WITH_ORIGIN).status_code == 422
    assert confirm(client, token).status_code == 204


def test_confirm_keeps_existing_verification_time(client, session, outbox):
    register(client)
    token = issue(client, outbox)
    verified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    user = session.scalar(select(User).where(User.email == EMAIL))
    user.email_verified_at = verified
    session.flush()
    assert confirm(client, token).status_code == 204
    session.refresh(user)
    assert user.email_verified_at == verified