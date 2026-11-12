"""Активные дни пользователей (для метрик закрытого тестирования).

Запись идёт после основной операции, отдельной короткой транзакцией и «на лучших
усилиях»: сбой записи не должен ломать действие пользователя."""

import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import User, UserActivity
from app.stats import user_zone

logger = logging.getLogger(__name__)


def record_activity(db: Session, user: User, now: datetime | None = None) -> None:
    """Отмечает сегодняшний (по поясу пользователя) день активным. Повтор безвреден.
    now с часовым поясом; нужен только тестам."""
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(user_zone(user.timezone)).date()
    try:
        db.execute(
            insert(UserActivity)
            .values(user_id=user.id, day=day)
            .on_conflict_do_nothing(index_elements=["user_id", "day"])
        )
        db.commit()
    except Exception as exc:  # намеренно широко: метрика не должна ломать действие
        db.rollback()
        logger.error("activity record failed: %s", type(exc).__name__)