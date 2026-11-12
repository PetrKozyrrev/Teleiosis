"""Напоминания по материалу: выбор, письмо, захват. Правила как у подборки:
собрать письмо, атомарно занять строку (UPDATE ... RETURNING, commit), затем отправить.
At-most-once: если отправка не удалась, повторов нет."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.digest import BATCH_LIMIT, SendFunction, clean_title
from app.mailer import send_email
from app.models import Content, Reminder, User
from app.unsubscribe import SecretKeyMissing, page_link, unsubscribe_headers

logger = logging.getLogger(__name__)

DONE_STATUSES = ("studied", "irrelevant")


def select_due_reminders(db: Session, now: datetime, limit: int):
    """Ожидающие напоминания, срок которых наступил, у пользователей, которым можно
    писать. Старые не отбрасываются: человек сам просил (решение 7.0)."""
    return db.execute(
        select(
            Reminder.id,
            Reminder.user_id,
            User.email,
            Content.id,
            Content.title,
            Content.status,
        )
        .join(User, User.id == Reminder.user_id)
        .join(Content, Content.id == Reminder.content_id)
        .where(
            Reminder.status == "pending",
            Reminder.scheduled_at <= now,
            User.reminders_enabled.is_(True),
            User.email_verified_at.is_not(None),
            User.email.is_not(None),
        )
        .order_by(Reminder.scheduled_at, Reminder.id)
        .limit(limit)
    ).all()


def build_reminder_email(user_id: int, content_id: int, title: str | None) -> tuple[str, str]:
    """(тема, текст). Только text/plain, ссылки только на наш сайт."""
    clean = clean_title(title)
    body = "\n".join(
        [
            "Здравствуйте!",
            "",
            "Вы просили напомнить об этом материале из вашей библиотеки Teleiosis:",
            "",
            clean,
            f"{settings.app_origin}/app/item.html?id={content_id}",
            "",
            "Отключить напоминания (включить обратно можно в настройках):",
            page_link(user_id),
        ]
    )
    return f"Teleiosis: напоминание: {clean}", body + "\n"


def claim_reminder(db: Session, reminder_id: int) -> bool:
    """Атомарно помечает напоминание отправленным. True получает ровно один процесс.
    Флаги пользователя проверяются заново в самом запросе."""
    allowed_users = select(User.id).where(
        User.reminders_enabled.is_(True), User.email_verified_at.is_not(None)
    )
    claimed = db.execute(
        update(Reminder)
        .where(
            Reminder.id == reminder_id,
            Reminder.status == "pending",
            Reminder.user_id.in_(allowed_users),
        )
        .values(status="sent")
        .returning(Reminder.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()
    return claimed is not None


def cancel_pending(db: Session, reminder_id: int) -> bool:
    """Отменяет ожидающее напоминание без письма. True, если отменил именно этот вызов."""
    cancelled = db.execute(
        update(Reminder)
        .where(Reminder.id == reminder_id, Reminder.status == "pending")
        .values(status="cancelled")
        .returning(Reminder.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()
    return cancelled is not None


@dataclass
class ReminderReport:
    sent: int = 0
    failed: int = 0
    cancelled: int = 0


def process_due_reminders(
    db: Session,
    now: datetime,
    send: SendFunction = send_email,
    limit: int = BATCH_LIMIT,
) -> ReminderReport:
    """Один проход воркера. now с часовым поясом; send и now подставляются тестами."""
    report = ReminderReport()
    for reminder_id, user_id, email, content_id, title, content_status in select_due_reminders(
        db, now, limit
    ):
        # Материал уже изучен или неактуален: напоминать не о чем
        if content_status in DONE_STATUSES:
            if cancel_pending(db, reminder_id):
                report.cancelled += 1
            continue

        # 1. Сборка. Ошибка здесь напоминание не расходует: повтор на следующем проходе.
        try:
            subject, body = build_reminder_email(user_id, content_id, title)
            headers = unsubscribe_headers(user_id)
            claimed = claim_reminder(db, reminder_id)
        except SecretKeyMissing:
            raise  # ошибка настройки: не маскируем под ошибку одного пользователя
        except Exception as exc:
            db.rollback()
            logger.error("reminder build failed (id %s): %s", reminder_id, type(exc).__name__)
            report.failed += 1
            continue
        if not claimed:
            continue

        # 2. Отправка. Строка уже занята: повторов нет.
        try:
            sent = send(email, subject, body, headers=headers)
        except Exception as exc:
            logger.error("reminder send crashed (id %s): %s", reminder_id, type(exc).__name__)
            sent = False
        if sent:
            report.sent += 1
        else:
            report.failed += 1
            logger.warning("reminder %s was not sent", reminder_id)
    return report