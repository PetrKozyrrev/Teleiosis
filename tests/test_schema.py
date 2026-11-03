import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import Category, Content, Reminder, User


def make_user(session, telegram_id=1):
    user = User(telegram_id=telegram_id)
    session.add(user)
    session.flush()
    return user


def make_content(session, user, **kwargs):
    data = {"title": "T", "url": "https://a.com/x", "url_normalized": "https://a.com/x"}
    data.update(kwargs)
    content = Content(user_id=user.id, **data)
    session.add(content)
    session.flush()
    return content


def test_defaults(session):
    user = make_user(session)
    session.refresh(user)
    assert user.timezone == "UTC"
    assert user.reminders_enabled is True
    content = make_content(session, user)
    session.refresh(content)
    assert content.status == "unseen"
    assert content.source == "other"


def test_telegram_id_unique(session):
    make_user(session, telegram_id=5)
    with pytest.raises(IntegrityError):
        make_user(session, telegram_id=5)


def test_duplicate_url_rejected(session):
    user = make_user(session)
    make_content(session, user)
    with pytest.raises(IntegrityError):
        make_content(session, user)


def test_same_url_for_different_users_allowed(session):
    make_content(session, make_user(session, 1))
    make_content(session, make_user(session, 2))


def test_notes_without_url_do_not_conflict(session):
    user = make_user(session)
    make_content(session, user, url=None, url_normalized=None, note="a")
    make_content(session, user, url=None, url_normalized=None, note="b")


def test_content_requires_url_or_note(session):
    user = make_user(session)
    with pytest.raises(IntegrityError):
        make_content(session, user, url=None, url_normalized=None, note=None)


def test_invalid_status_rejected(session):
    user = make_user(session)
    with pytest.raises(IntegrityError):
        make_content(session, user, status="done")


def test_invalid_reminder_status_rejected(session):
    user = make_user(session)
    content = make_content(session, user)
    with pytest.raises(IntegrityError):
        session.add(
            Reminder(
                user_id=user.id,
                content_id=content.id,
                scheduled_at=text("now()"),
                status="weird",
            )
        )
        session.flush()


def test_category_name_unique_per_user(session):
    user = make_user(session)
    session.add(Category(user_id=user.id, name="Бизнес"))
    session.flush()
    with pytest.raises(IntegrityError):
        session.add(Category(user_id=user.id, name="Бизнес"))
        session.flush()


def test_category_name_length(session):
    user = make_user(session)
    with pytest.raises(IntegrityError):
        session.add(Category(user_id=user.id, name=""))
        session.flush()


def test_delete_category_keeps_content(session):
    user = make_user(session)
    category = Category(user_id=user.id, name="Маркетинг")
    session.add(category)
    session.flush()
    content = make_content(session, user, category_id=category.id)

    session.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category.id})
    session.refresh(content)
    assert content.category_id is None


def test_delete_content_removes_reminders(session):
    user = make_user(session)
    content = make_content(session, user)
    session.add(
        Reminder(user_id=user.id, content_id=content.id, scheduled_at=text("now()"))
    )
    session.flush()

    session.execute(text("DELETE FROM contents WHERE id = :id"), {"id": content.id})
    assert session.execute(select(Reminder)).first() is None


def test_delete_user_cascades(session):
    user = make_user(session)
    session.add(Category(user_id=user.id, name="X"))
    content = make_content(session, user)
    session.add(
        Reminder(user_id=user.id, content_id=content.id, scheduled_at=text("now()"))
    )
    session.flush()

    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    for model in (Category, Content, Reminder):
        assert session.execute(select(model)).first() is None