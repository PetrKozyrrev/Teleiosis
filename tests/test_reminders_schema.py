import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Content, Reminder, User


def make_user(session, telegram_id=1):
    user = User(telegram_id=telegram_id)
    session.add(user)
    session.flush()
    return user


def make_content(session, user, note="x"):
    content = Content(user_id=user.id, title="T", note=note)
    session.add(content)
    session.flush()
    return content


def add(session, user, content, status="pending"):
    row = Reminder(
        user_id=user.id, content_id=content.id, scheduled_at=text("now()"), status=status
    )
    session.add(row)
    session.flush()
    return row


def test_two_pending_for_one_material_rejected(session):
    user = make_user(session)
    content = make_content(session, user)
    add(session, user, content)
    with pytest.raises(IntegrityError):
        add(session, user, content)


def test_history_rows_do_not_conflict(session):
    user = make_user(session)
    content = make_content(session, user)
    add(session, user, content, "sent")
    add(session, user, content, "sent")
    add(session, user, content, "cancelled")
    add(session, user, content, "pending")


def test_pending_for_different_materials_allowed(session):
    user = make_user(session)
    add(session, user, make_content(session, user, "a"))
    add(session, user, make_content(session, user, "b"))