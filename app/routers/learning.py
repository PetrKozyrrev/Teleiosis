from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models import Content, ReviewCard, StudyTask
from app.routers.review import due_card_filters
from app.schemas import ContentOut
from app.stats import calendar_week_start, studied_materials, user_zone

router = APIRouter(prefix="/mobile/learning", tags=["learning"])

Reason = Literal["overdue_task", "today_task", "studied_task", "planned_material", "unseen_material"]
LibraryState = Literal["available", "empty", "scheduled_later", "no_recommendation"]


class NextAction(BaseModel):
    material_id: int
    task_id: int | None = None
    title: str
    source: str
    content_type: str
    reason: Reason
    duration_minutes: int | None
    task_day: date | None = None


class WeeklyProgress(BaseModel):
    week_start: date
    weekly_goal: int
    weekly_completed: int
    tasks_total: int
    tasks_done: int


class TodayOut(BaseModel):
    local_date: date
    timezone: str
    next_action: NextAction | None
    library_state: LibraryState
    due_review_count: int
    weekly_progress: WeeklyProgress


def material_action(material: Content, reason: Reason, task: StudyTask | None = None) -> NextAction:
    if task is not None:
        duration = task.minutes
    elif material.video_duration_seconds and material.video_duration_seconds > 0:
        duration = (material.video_duration_seconds + 59) // 60
    else:
        duration = ContentOut.model_validate(material).reading_minutes
    return NextAction(
        material_id=material.id, title=material.title, source=material.source, content_type=material.content_type,
        task_id=task.id if task else None, task_day=task.day if task else None,
        reason=reason, duration_minutes=duration,
    )


def select_next_action(db: Session, owner_id: int, local_day: date) -> tuple[NextAction | None, LibraryState]:
    open_tasks = (StudyTask.user_id == owner_id, StudyTask.completed_at.is_(None))
    owned = Content.user_id == owner_id
    task = db.execute(
        select(StudyTask, Content)
        .join(Content, and_(Content.id == StudyTask.content_id, Content.user_id == StudyTask.user_id))
        .where(*open_tasks, StudyTask.day <= local_day, Content.status != "irrelevant")
        .order_by(StudyTask.day, StudyTask.priority, StudyTask.id)
        .limit(1)
    ).first()
    if task is not None:
        entry, material = task
        reason = "studied_task" if material.status == "studied" else (
            "overdue_task" if entry.day < local_day else "today_task"
        )
        return material_action(material, reason, entry), "available"

    candidates = select(Content).where(owned, Content.status.in_(("planned", "unseen")))
    future_task = select(StudyTask.id).where(
        *open_tasks, StudyTask.content_id == Content.id, StudyTask.day > local_day,
    ).exists()
    material = db.scalar(
        candidates.where(~future_task)
        .order_by(Content.status != "planned", Content.created_at, Content.id)
        .limit(1)
    )
    if material is not None:
        reason = "planned_material" if material.status == "planned" else "unseen_material"
        return material_action(material, reason), "available"

    has_materials, has_future = db.execute(select(
        select(Content.id).where(owned).exists(),
        select(Content.id).where(owned, Content.status != "irrelevant", future_task).exists(),
    )).one()
    if has_future:
        return None, "scheduled_later"
    return None, "no_recommendation" if has_materials else "empty"


@router.get("/today", response_model=TodayOut)
def read_today(db: DbSession, user: CurrentUser) -> TodayOut:
    zone = user_zone(user.timezone)
    local_day = datetime.now(zone).date()
    week_start = calendar_week_start(local_day)
    week_end = week_start + timedelta(days=7)
    action, library_state = select_next_action(db, user.id, local_day)
    due = db.scalar(select(func.count()).select_from(ReviewCard).where(
        ReviewCard.user_id == user.id, *due_card_filters(local_day),
    ))
    completed = db.scalar(select(func.count()).select_from(Content).where(
        *studied_materials(user),
        Content.studied_at >= datetime.combine(week_start, time.min, tzinfo=zone),
        Content.studied_at < datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=zone),
    ))
    tasks_total, tasks_done = db.execute(select(func.count(), func.count(StudyTask.completed_at)).where(
        StudyTask.user_id == user.id, StudyTask.day >= week_start, StudyTask.day < week_end,
    )).one()
    return TodayOut(
        local_date=local_day, timezone=zone.key, next_action=action, library_state=library_state,
        due_review_count=due, weekly_progress=WeeklyProgress(
            week_start=week_start, weekly_goal=user.weekly_reading_goal, weekly_completed=completed,
            tasks_total=tasks_total, tasks_done=tasks_done,
        ),
    )
