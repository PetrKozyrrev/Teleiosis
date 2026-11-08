from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import User
from app.sessions import create_session


def add_user(session, **fields):
    user = User(**fields)
    session.add(user)
    session.flush()
    return user


def test_email_only_user_allowed_with_defaults(session):
    user = add_user(session, email="ivan@example.com")
    session.refresh(user)
    assert user.telegram_id is None
    assert user.password_hash is None
    assert user.email_verified_at is None
    assert user.consent_at is None
    assert user.timezone == "UTC"
    assert user.reminders_enabled is True


def test_telegram_only_user_still_allowed(session):
    assert add_user(session, telegram_id=7).email is None


def test_user_without_any_login_method_rejected(session):
    with pytest.raises(IntegrityError):
        add_user(session)


def test_several_users_without_telegram_id_allowed(session):
    add_user(session, email="a@example.com")
    add_user(session, email="b@example.com")


def test_email_unique(session):
    add_user(session, email="a@example.com")
    with pytest.raises(IntegrityError):
        add_user(session, email="a@example.com")


def test_email_must_be_lowercase(session):
    with pytest.raises(IntegrityError):
        add_user(session, email="Ivan@Example.com")


def test_email_too_long_rejected(session):
    long_email = "a" * 250 + "@x.co"  # 255 символов
    assert len(long_email) == 255
    with pytest.raises(IntegrityError):
        add_user(session, email=long_email)


def test_password_hash_requires_email(session):
    with pytest.raises(IntegrityError):
        add_user(session, telegram_id=5, password_hash="x")


def test_password_hash_with_email_allowed(session):
    add_user(session, email="a@example.com", password_hash="hash")


def test_consent_fields_come_as_a_pair(session):
    with pytest.raises(IntegrityError):
        add_user(
            session,
            email="a@example.com",
            consent_at=datetime.now(timezone.utc),
        )


def test_consent_pair_allowed(session):
    user = add_user(
        session,
        email="a@example.com",
        consent_at=datetime.now(timezone.utc),
        consent_version="2026-11-08",
    )
    assert user.consent_version == "2026-11-08"


def test_me_for_email_user_has_no_telegram_id(client, session):
    user = add_user(session, email="a@example.com", password_hash="hash")
    token, _ = create_session(session, user)
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["telegram_id"] is None
    assert body["email"] == "a@example.com"
    assert "password_hash" not in body