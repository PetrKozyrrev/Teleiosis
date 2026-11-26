from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.deps import CurrentUser, DbSession
from app.duration import estimated_minutes_sql
from app.models import Content, StudyGoal, StudyGoalMaterial, StudyTask
from app.stats import user_zone

router = APIRouter(prefix="/mobile/learning", tags=["learning"])
Budget = Literal["5", "15", "30", "60"]
Limit = Annotated[int, Query(ge=1, le=3)]


class Recommendation(BaseModel):
    material_id: int
    title: str
    source: str
    content_type: str
    status: Literal["unseen", "planned"]
    duration_minutes: int
    reason: Literal["overdue_task", "today_task", "active_goal", "fits_time"]
    goal_name: str | None
    task_id: int | None
    task_day: date | None


class BudgetOut(BaseModel):
    budget_minutes: int
    local_date: date
    items: list[Recommendation]
    has_unknown_duration: bool


@router.get("/time-budget", response_model=BudgetOut)
def recommendations(db: DbSession, user: CurrentUser, budget_minutes: Budget, limit: Limit = 3):
    budget = int(budget_minutes)
    day = datetime.now(user_zone(user.timezone)).date()
    open_tasks = (StudyTask.user_id == user.id, StudyTask.completed_at.is_(None))
    due = select(StudyTask.content_id, StudyTask.id.label("task_id"), StudyTask.day.label("task_day")).where(
        *open_tasks, StudyTask.day <= day,
    ).ext(distinct_on(StudyTask.content_id)).order_by(
        StudyTask.content_id, StudyTask.day, StudyTask.priority, StudyTask.id,
    ).subquery()
    future = select(StudyTask.content_id).where(*open_tasks, StudyTask.day > day).distinct().subquery()
    active = select(StudyGoalMaterial.content_id, StudyGoal.name.label("goal_name")).join(
        StudyGoal, and_(StudyGoal.id == StudyGoalMaterial.goal_id, StudyGoal.user_id == StudyGoalMaterial.user_id),
    ).where(StudyGoalMaterial.user_id == user.id, StudyGoal.status == "active").ext(
        distinct_on(StudyGoalMaterial.content_id),
    ).order_by(StudyGoalMaterial.content_id, StudyGoal.id).subquery()
    eligible = (Content.user_id == user.id, Content.status.in_(("planned", "unseen")))
    # Compute the estimate once per candidate before applying the limit and sort.
    sized = select(Content.id.label("material_id"), Content.title, Content.source, Content.content_type,
                   Content.status, Content.created_at, estimated_minutes_sql().label("duration_minutes")
    ).where(*eligible).cte("sized_materials").prefix_with("MATERIALIZED", dialect="postgresql")
    duration = sized.c.duration_minutes
    rows = db.execute(
        select(sized.c.material_id, sized.c.title, sized.c.source, sized.c.content_type, sized.c.status,
               duration, active.c.goal_name, due.c.task_id, due.c.task_day)
        .outerjoin(due, due.c.content_id == sized.c.material_id)
        .outerjoin(future, future.c.content_id == sized.c.material_id)
        .outerjoin(active, active.c.content_id == sized.c.material_id)
        .where(duration <= budget, (future.c.content_id.is_(None) | due.c.task_id.is_not(None)))
        .order_by(due.c.task_id.is_not(None).desc(), active.c.goal_name.is_not(None).desc(),
                  duration.desc(), sized.c.created_at, sized.c.material_id)
        .limit(limit)
    ).mappings()
    items = []
    for row in rows:
        if row.task_day is not None:
            reason = "overdue_task" if row.task_day < day else "today_task"
        else:
            reason = "active_goal" if row.goal_name is not None else "fits_time"
        items.append(dict(row, reason=reason))
    unknown = db.scalar(select(select(Content.id).where(
        *eligible, estimated_minutes_sql(normalize_notes=False).is_(None),
    ).exists()))
    return {"budget_minutes": budget, "local_date": day, "items": items, "has_unknown_duration": unknown}
