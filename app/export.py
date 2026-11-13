"""Выгрузка данных пользователя (право на получение копии данных).

В выгрузку входит содержимое пользователя и его профиль. Хэш пароля, сессии,
токены и технические журналы не входят. Всё собирается в памяти: для закрытого
теста этого достаточно."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Content, Reminder, User, UserActivity

EXPORT_VERSION = 1


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def build_export(db: Session, user: User, now: datetime | None = None) -> dict:
    """now с часовым поясом; нужен только тестам."""
    now = now or datetime.now(timezone.utc)

    categories = db.scalars(
        select(Category).where(Category.user_id == user.id).order_by(Category.id)
    ).all()
    contents = db.scalars(
        select(Content).where(Content.user_id == user.id).order_by(Content.id)
    ).all()
    reminders = db.scalars(
        select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.id)
    ).all()
    days = db.scalars(
        select(UserActivity.day)
        .where(UserActivity.user_id == user.id)
        .order_by(UserActivity.day)
    ).all()

    return {
        "version": EXPORT_VERSION,
        "exported_at": _iso(now),
        "user": {
            "id": user.id,
            "email": user.email,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "email_verified_at": _iso(user.email_verified_at),
            "consent_at": _iso(user.consent_at),
            "consent_version": user.consent_version,
            "timezone": user.timezone,
            "reminders_enabled": user.reminders_enabled,
            "reminder_time": user.reminder_time.strftime("%H:%M"),
            "created_at": _iso(user.created_at),
        },
        "categories": [
            {"id": c.id, "name": c.name, "created_at": _iso(c.created_at)}
            for c in categories
        ],
        "contents": [
            {
                "id": c.id,
                "category_id": c.category_id,
                "title": c.title,
                "url": c.url,
                "description": c.description,
                "note": c.note,
                "content_type": c.content_type,
                "source": c.source,
                "image_url": c.image_url,
                "status": c.status,
                "studied_at": _iso(c.studied_at),
                "last_opened_at": _iso(c.last_opened_at),
                "open_count": c.open_count,
                "created_at": _iso(c.created_at),
                "updated_at": _iso(c.updated_at),
            }
            for c in contents
        ],
        "reminders": [
            {
                "id": r.id,
                "content_id": r.content_id,
                "scheduled_at": _iso(r.scheduled_at),
                "status": r.status,
                "created_at": _iso(r.created_at),
            }
            for r in reminders
        ],
        "activity_days": [day.isoformat() for day in days],
    }