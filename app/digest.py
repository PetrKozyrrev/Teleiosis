"""Ежедневная подборка: когда пора, какие материалы, текст письма, захват отправки.

Политика at-most-once: сначала подборка собирается, затем день атомарно
захватывается (UPDATE ... RETURNING, commit), и только потом письмо уходит.
Если отправка не удалась, повторять её в MVP не будем."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.mailer import send_email
from app.models import Content, User
from app.stats import user_zone
from app.unsubscribe import SecretKeyMissing, page_link, unsubscribe_headers

logger = logging.getLogger(__name__)

DIGEST_SIZE = 5
CATCHUP_MINUTES = 180  # сколько после reminder_time подборку ещё можно отправить
BATCH_LIMIT = 50  # не больше писем за один проход воркера
TITLE_MAX = 100
PENDING_STATUSES = ("planned", "unseen")

SendFunction = Callable[..., bool]


def is_due(local_now: datetime, reminder_time: time, last_digest_on: date | None) -> bool:
    """Пора ли отправлять. local_now это время в поясе пользователя.

    Сравниваются «часы на стене» (минуты от полуночи), а не строится datetime:
    перевод часов не ломает логику. Окно не переходит за конец местных суток."""
    if last_digest_on is not None and last_digest_on >= local_now.date():
        return False
    start = reminder_time.hour * 60 + reminder_time.minute
    current = local_now.hour * 60 + local_now.minute
    return 0 <= current - start < CATCHUP_MINUTES


def clean_title(title: str | None) -> str:
    """Название приходит с чужого сайта: схлопываем пробелы и переводы строк,
    убираем управляющие и невидимые символы, обрезаем."""
    text = " ".join((title or "").split())
    text = "".join(ch for ch in text if ch.isprintable())
    if not text:
        return "Без названия"
    if len(text) > TITLE_MAX:
        text = text[: TITLE_MAX - 1] + "…"
    return text


def pick_materials(db: Session, user_id: int) -> tuple[list[tuple[int, str]], int]:
    """(материалы подборки, сколько всего ждёт изучения).
    Сначала planned, потом unseen, старые первыми."""
    rank = case((Content.status == "planned", 0), else_=1)
    rows = db.execute(
        select(Content.id, Content.title)
        .where(Content.user_id == user_id, Content.status.in_(PENDING_STATUSES))
        .order_by(rank, Content.created_at, Content.id)
        .limit(DIGEST_SIZE)
    ).all()
    if not rows:
        return [], 0
    pending = db.scalar(
        select(func.count())
        .select_from(Content)
        .where(Content.user_id == user_id, Content.status.in_(PENDING_STATUSES))
    )
    return [(row[0], row[1]) for row in rows], pending


def build_digest_email(
    user_id: int, items: list[tuple[int, str]], pending: int
) -> tuple[str, str]:
    """(тема, текст). Только text/plain, ссылки только на наш сайт."""
    lines = ["Здравствуйте!", "", "Из вашей библиотеки Teleiosis на сегодня:", ""]
    for number, (content_id, title) in enumerate(items, start=1):
        lines.append(f"{number}. {clean_title(title)}")
        lines.append(f"   {settings.app_origin}/app/item.html?id={content_id}")
    lines.append("")
    more = pending - len(items)
    if more > 0:
        lines.append(f"И ещё {more} в библиотеке: {settings.app_origin}/app/")
        lines.append("")
    lines += [
        "Не откладывайте на завтра то, что можно узнать сегодня.",
        "",
        "Отключить напоминания (включить обратно можно в настройках):",
        page_link(user_id),
    ]
    return "Teleiosis: что изучить сегодня", "\n".join(lines) + "\n"


def claim_digest(db: Session, user_id: int, local_date: date) -> bool:
    """Атомарно занимает местный день. True получает ровно один процесс.
    Условия отписки и подтверждения проверяются заново в самом запросе."""
    claimed = db.execute(
        update(User)
        .where(
            User.id == user_id,
            User.reminders_enabled.is_(True),
            User.email_verified_at.is_not(None),
            or_(User.last_digest_on.is_(None), User.last_digest_on < local_date),
        )
        .values(last_digest_on=local_date)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()
    return claimed is not None


@dataclass
class DigestReport:
    sent: int = 0
    failed: int = 0


def process_due_users(
    db: Session,
    now: datetime,
    send: SendFunction = send_email,
    limit: int = BATCH_LIMIT,
) -> DigestReport:
    """Один проход воркера. now должен быть с часовым поясом (UTC).
    send и now подставляются только тестами."""
    report = DigestReport()
    candidates = db.execute(
        select(
            User.id, User.email, User.timezone, User.reminder_time, User.last_digest_on
        )
        .where(
            User.reminders_enabled.is_(True),
            User.email_verified_at.is_not(None),
            User.email.is_not(None),
        )
        .order_by(User.id)
    ).all()

    for user_id, email, timezone_name, reminder_time, last_digest_on in candidates:
        if report.sent + report.failed >= limit:
            break
        local_now = now.astimezone(user_zone(timezone_name))
        if not is_due(local_now, reminder_time, last_digest_on):
            continue

        # 1. Сборка. Ошибка здесь день не расходует: на следующем проходе повтор.
        try:
            items, pending = pick_materials(db, user_id)
            if not items:
                continue  # нечего слать, день остаётся свободным
            subject, body = build_digest_email(user_id, items, pending)
            headers = unsubscribe_headers(user_id)
            claimed = claim_digest(db, user_id, local_now.date())
        except SecretKeyMissing:
            raise  # ошибка настройки: не маскируем под ошибку одного пользователя
        except Exception as exc:
            db.rollback()
            logger.error("digest build failed for user %s: %s", user_id, type(exc).__name__)
            report.failed += 1
            continue
        if not claimed:
            continue  # другой процесс, отписка или подтверждение изменились

        # 2. Отправка. День уже занят: повторов нет.
        try:
            sent = send(email, subject, body, headers=headers)
        except Exception as exc:
            logger.error("digest send crashed for user %s: %s", user_id, type(exc).__name__)
            sent = False
        if sent:
            report.sent += 1
        else:
            report.failed += 1
            logger.warning("digest was not sent to user %s", user_id)
    return report