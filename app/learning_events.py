"""First-party observations. A failed event write leaves the domain transaction usable."""

import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LearningEvent, User
from app.stats import user_zone

ClientEventName = Literal[
    "today_viewed", "next_action_opened", "saved_material_reopened", "time_budget_selected", "recommendation_opened",
]
ServerEventName = Literal[
    "registration_completed", "material_saved", "material_studied", "goal_created",
    "goal_material_linked", "study_reflection_saved", "review_card_created", "review_completed",
]
logger = logging.getLogger(__name__)


def record_learning_event(
    db: Session, user: User, name: ClientEventName | ServerEventName, key: str | int | UUID, *,
    material_id: int | None = None, visit_id: UUID | None = None, budget_minutes: int | None = None,
    has_results: bool | None = None, now: datetime | None = None,
) -> None:
    if not settings.learning_metrics_enabled:
        return
    now = now or datetime.now(timezone.utc)
    statement = insert(LearningEvent).values(
        user_id=user.id, name=name, dedupe_key=str(key), occurred_at=now,
        local_day=now.astimezone(user_zone(user.timezone)).date(), material_id=material_id,
        visit_id=visit_id, budget_minutes=budget_minutes, has_results=has_results,
    ).on_conflict_do_nothing(constraint="uq_learning_event_once")
    try:
        connection = db.connection()
        with connection.begin_nested():
            connection.execute(statement)
    except SQLAlchemyError as exc:
        logger.error("learning event write failed: %s", type(exc).__name__)
