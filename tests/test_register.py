import pytest
from sqlalchemy import select

from app.models import User
from app.passwords import verify_password
from app.routers.auth import CONSENT_VERSION
from tests.helpers import ORIGIN

GOOD_PASSWORD = "correct horse battery"


def register(client, **overrides):
    body = {"email": "ivan@example.com", "password": GOOD_PASSWORD, "consent": True}
    body.update(overrides)
    return client.post("/auth/register", json=body, headers={"Origin": ORIGIN})


def test_register_creates_user(client, session):
    response = register(client)
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["email"] == "ivan@example.com"
    assert body["telegram_id"] is None
    assert "password" not in body
    assert "password_hash" not in body

    user = session.scalar(select(User).where(User.email == "ivan@example.com"))
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != GOOD_PASSWORD
    assert verify_password(GOOD_PASSWORD, user.password_hash)
    assert user.consent_at is not None
    assert user.consent_version == CONSENT_VERSION
    assert user.email_verified_at is None


def test_email_is_normalized(client):
    body = register(client, email="  Ivan@Example.COM ").json()
    assert body["email"] == "ivan@example.com"


def test_duplicate_email_conflict_ignores_case(client):
    assert register(client).status_code == 201
    response = register(client, email="IVAN@example.com")
    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}


def test_unicode_password_works(client, session):
    password = "пароль-из-кириллицы"
    assert register(client, password=password).status_code == 201
    user = session.scalar(select(User).where(User.email == "ivan@example.com"))
    assert verify_password(password, user.password_hash)


@pytest.mark.parametrize("email", ["", "plain", "a@", "@example.com", "a b@example.com"])
def test_invalid_email_rejected(client, email):
    assert register(client, email=email).status_code == 422


def test_password_length_limits(client):
    assert register(client, password="x" * 9).status_code == 422
    assert register(client, email="a@example.com", password="x" * 129).status_code == 422
    assert register(client, email="b@example.com", password="x" * 10).status_code == 201
    assert register(client, email="c@example.com", password="x" * 128).status_code == 201


def test_password_is_not_trimmed(client, session):
    padded = "  spaced password  "
    assert register(client, password=padded).status_code == 201
    user = session.scalar(select(User).where(User.email == "ivan@example.com"))
    assert verify_password(padded, user.password_hash)
    assert not verify_password(padded.strip(), user.password_hash)


def test_consent_required(client):
    assert register(client, consent=False).status_code == 422
    body = {"email": "ivan@example.com", "password": GOOD_PASSWORD}
    assert (client.post("/auth/register", json=body, headers={"Origin": ORIGIN}).status_code== 422)


def test_unknown_fields_rejected(client):
    assert register(client, telegram_id=5).status_code == 422
    assert register(client, email_verified_at="2026-01-01T00:00:00Z").status_code == 422