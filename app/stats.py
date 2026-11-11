"""Статистика пользователя: страница «Прогресс» и строка над библиотекой.

Окно «7 дней» это сегодняшний и шесть предыдущих локальных дней пользователя.
Дни считаются в Python (zoneinfo), а не в SQL: неверное название пояса
не должно ронять запрос."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Content, User

DAYS = 7
TOP_CATEGORIES = 5
STATUSES = ("unseen", "planned", "studied", "irrelevant")


def user_zone(name: str) -> ZoneInfo:
    """Пояс пользователя; если название не читается, UTC."""
    try:
        return ZoneInfo(name)
    except (ValueError, OSError, KeyError):
        return ZoneInfo("UTC")


def share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def compute_stats(db: Session, user: User, now: datetime | None = None) -> dict:
    """now должен быть с часовым поясом; нужен только тестам."""
    now = now or datetime.now(timezone.utc)
    zone = user_zone(user.timezone)
    today = now.astimezone(zone).date()
    days = [today - timedelta(days=offset) for offset in range(DAYS - 1, -1, -1)]
    window_start = datetime.combine(days[0], time.min, tzinfo=zone).astimezone(
        timezone.utc
    )

    # 1. Материалы по статусам
    by_status = dict.fromkeys(STATUSES, 0)
    status_rows = db.execute(
        select(Content.status, func.count())
        .where(Content.user_id == user.id)
        .group_by(Content.status)
    )
    for status_value, amount in status_rows:
        if status_value in by_status:
            by_status[status_value] = amount
    total = sum(by_status.values())

    # 2. Возвраты: только материалы со ссылкой (заметку открыть нельзя)
    with_url, opened = db.execute(
        select(
            func.count(Content.id).filter(Content.url.is_not(None)),
            func.count(Content.id).filter(
                Content.url.is_not(None), Content.open_count > 0
            ),
        ).where(Content.user_id == user.id)
    ).one()

    # 3. Популярные категории
    category_rows = db.execute(
        select(Category.id, Category.name, func.count(Content.id))
        .join(Content, Content.category_id == Category.id)
        .where(Category.user_id == user.id, Content.user_id == user.id)
        .group_by(Category.id, Category.name)
        .order_by(
            func.count(Content.id).desc(), func.lower(Category.name), Category.id
        )
        .limit(TOP_CATEGORIES)
    ).all()

    # 4. Динамика по локальным дням: берём только метки времени за окно
    added = dict.fromkeys(days, 0)
    studied = dict.fromkeys(days, 0)
    created_rows = db.execute(
        select(Content.created_at).where(
            Content.user_id == user.id, Content.created_at >= window_start
        )
    )
    for (moment,) in created_rows:
        day = moment.astimezone(zone).date()
        if day in added:
            added[day] += 1
    studied_rows = db.execute(
        select(Content.studied_at).where(
            Content.user_id == user.id, Content.studied_at >= window_start
        )
    )
    for (moment,) in studied_rows:
        day = moment.astimezone(zone).date()
        if day in studied:
            studied[day] += 1

    return {
        "total": total,
        "by_status": by_status,
        "studied_share": share(by_status["studied"], total - by_status["irrelevant"]),
        "with_url": with_url,
        "opened": opened,
        "return_share": share(opened, with_url),
        "added_7d": sum(added.values()),
        "studied_7d": sum(studied.values()),
        "top_categories": [
            {"id": row[0], "name": row[1], "count": row[2]} for row in category_rows
        ],
        "days": [
            {"day": day, "added": added[day], "studied": studied[day]} for day in days
        ],
    }