from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import Reminder
from app.routers.contents import ContentId, get_own_content
from app.schemas import ReminderOut, ReminderSet

router = APIRouter(prefix="/contents", tags=["reminders"])

MAX_PENDING_PER_USER = 100
MAX_AHEAD = timedelta(days=366)


def pending_reminder(db: DbSession, user: CurrentUser, content_id: int) -> Reminder | None:
    return db.scalar(
        select(Reminder).where(
            Reminder.content_id == content_id,
            Reminder.user_id == user.id,
            Reminder.status == "pending",
        )
    )


@router.get("/{content_id}/reminder", response_model=ReminderOut | None)
def read_reminder(content_id: ContentId, db: DbSession, user: CurrentUser):
    """Ожидающее напоминание материала или null."""
    get_own_content(db, user, content_id)
    return pending_reminder(db, user, content_id)


@router.put("/{content_id}/reminder", response_model=ReminderOut)
def set_reminder(
    content_id: ContentId, data: ReminderSet, db: DbSession, user: CurrentUser
):
    """Создаёт ожидающее напоминание или переносит существующее."""
    get_own_content(db, user, content_id)

    now = datetime.now(timezone.utc)
    if data.scheduled_at <= now:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Reminder time must be in the future"
        )
    if data.scheduled_at > now + MAX_AHEAD:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Reminder time must be within a year from now",
        )

    reminder = pending_reminder(db, user, content_id)
    if reminder is None:
        pending = db.scalar(
            select(func.count())
            .select_from(Reminder)
            .where(Reminder.user_id == user.id, Reminder.status == "pending")
        )
        if pending >= MAX_PENDING_PER_USER:
            raise HTTPException(status.HTTP_409_CONFLICT, "Too many pending reminders")
        reminder = Reminder(
            user_id=user.id, content_id=content_id, scheduled_at=data.scheduled_at
        )
        db.add(reminder)
    else:
        reminder.scheduled_at = data.scheduled_at

    try:
        db.commit()
    except IntegrityError:
        # Редкая гонка: два запроса одновременно создали напоминание
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Reminder was changed at the same time, repeat"
        )
    db.refresh(reminder)
    return reminder


@router.delete("/{content_id}/reminder", status_code=status.HTTP_204_NO_CONTENT)
def cancel_reminder(content_id: ContentId, db: DbSession, user: CurrentUser):
    """Отменяет ожидающее напоминание (строка остаётся со статусом cancelled)."""
    get_own_content(db, user, content_id)
    reminder = pending_reminder(db, user, content_id)
    if reminder is not None:
        reminder.status = "cancelled"
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)