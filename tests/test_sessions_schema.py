import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import AuthSession, User

HASH_A = "a" * 64
HASH_B = "b" * 64
IN_A_DAY = text("now() + interval '1 day'")


def make_user(session, telegram_id=1):
    user = User(telegram_id=telegram_id)
    session.add(user)
    session.flush()
    return user


def make_session(session, user, token_hash=HASH_A, expires_at=IN_A_DAY):
    row = AuthSession(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    session.add(row)
    session.flush()
    return row


def test_valid_session_saved(session):
    user = make_user(session)
    row = make_session(session, user)
    session.refresh(row)
    assert row.created_at is not None
    assert row.expires_at > row.created_at


def test_token_hash_unique(session):
    user = make_user(session)
    make_session(session, user, HASH_A)
    with pytest.raises(IntegrityError):
        make_session(session, user, HASH_A)


def test_several_sessions_per_user_allowed(session):
    user = make_user(session)
    make_session(session, user, HASH_A)
    make_session(session, user, HASH_B)


@pytest.mark.parametrize("bad_hash", ["", "abc", "a" * 63, "a" * 65])
def test_hash_length_enforced(session, bad_hash):
    user = make_user(session)
    with pytest.raises(IntegrityError):
        make_session(session, user, bad_hash)


def test_expiry_must_be_after_creation(session):
    user = make_user(session)
    with pytest.raises(IntegrityError):
        make_session(session, user, expires_at=text("now() - interval '1 hour'"))


def test_delete_user_removes_sessions(session):
    user = make_user(session)
    make_session(session, user)
    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert session.execute(select(AuthSession)).first() is None