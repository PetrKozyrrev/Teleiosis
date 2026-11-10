import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import EmailVerificationToken, User

HASH_A = "a" * 64
HASH_B = "b" * 64
IN_A_DAY = text("now() + interval '1 day'")


def make_user(session):
    user = User(email="a@example.com")
    session.add(user)
    session.flush()
    return user


def make_token(session, user, token_hash=HASH_A, expires_at=IN_A_DAY):
    row = EmailVerificationToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    session.add(row)
    session.flush()
    return row


def test_valid_token_saved(session):
    row = make_token(session, make_user(session))
    session.refresh(row)
    assert row.created_at is not None
    assert row.expires_at > row.created_at


def test_token_hash_unique(session):
    user = make_user(session)
    make_token(session, user, HASH_A)
    with pytest.raises(IntegrityError):
        make_token(session, user, HASH_A)


def test_several_tokens_per_user_allowed_by_schema(session):
    user = make_user(session)
    make_token(session, user, HASH_A)
    make_token(session, user, HASH_B)


@pytest.mark.parametrize("bad_hash", ["", "abc", "a" * 63, "a" * 65])
def test_hash_length_enforced(session, bad_hash):
    with pytest.raises(IntegrityError):
        make_token(session, make_user(session), bad_hash)


def test_expiry_must_be_after_creation(session):
    with pytest.raises(IntegrityError):
        make_token(session, make_user(session), expires_at=text("now() - interval '1 hour'"))


def test_delete_user_removes_tokens(session):
    user = make_user(session)
    make_token(session, user)
    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert session.execute(select(EmailVerificationToken)).first() is None