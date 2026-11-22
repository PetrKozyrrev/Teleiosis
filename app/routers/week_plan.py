import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BeforeValidator, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models import Content, StudyGoal, StudyTask, StudyTaskEvent, WeekBudget
from app.routers.contents import ContentId, get_own_content
from app.routers.organization import lock_owner
from app.schemas import MAX_BIGINT
from app.stats import user_zone

router = APIRouter(prefix="/mobile/plan", tags=["plan"])


def calendar_value(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Expected YYYY-MM-DD")
    return value


PlanDay = Annotated[date, BeforeValidator(calendar_value), Field(ge=date(1900, 1, 1), le=date(2100, 12, 31))]
ObjectId = Annotated[int, Field(strict=True, gt=0, le=MAX_BIGINT)]
Version = Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]{0,9}"$')]
BudgetMinutes = Annotated[int, Field(strict=True, ge=1, le=10080)]


class Write(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalInput(Write):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")]


class BudgetInput(Write):
    minutes: BudgetMinutes
    previous: BudgetMinutes | None


class TaskInput(Write):
    goal_id: ObjectId
    content_id: ObjectId
    day: PlanDay
    minutes: Annotated[int, Field(strict=True, ge=1, le=1440)]
    priority: Annotated[int, Field(strict=True, ge=1, le=3)]


class MoveInput(Write):
    day: PlanDay


def owned(db, model, owner, key):
    value = db.scalar(select(model).where(model.user_id == owner, model.id == key).with_for_update())
    if value is None:
        raise HTTPException(404, "Plan entry not found")
    return value


def matches(task, version):
    if version != f'"{task.version}"':
        raise HTTPException(412, "Plan entry changed")


def record(db, task, kind):
    db.add(StudyTaskEvent(task_id=task.id, version=task.version, kind=kind, day=task.day))


def task_out(task):
    return {key: getattr(task, key) for key in
            ("id", "goal_id", "content_id", "day", "minutes", "priority", "completed_at", "version")}


def summarize(tasks):
    done = [task for task in tasks if task["completed_at"] is not None]
    planned = [task for task in tasks if task["completed_at"] is None]
    next_task = min(planned, key=lambda task: (task["priority"], task["day"], task["id"]), default=None)
    return {"total": len(tasks), "done": len(done),
            "planned_minutes": sum(task["minutes"] for task in tasks),
            "done_minutes": sum(task["minutes"] for task in done),
            "next_id": next_task["id"] if next_task else None}


@router.get("")
def read_week(db: DbSession, user: CurrentUser, day: PlanDay | None = None):
    today = datetime.now(user_zone(user.timezone)).date()
    anchor = day or today
    start = anchor - timedelta(days=anchor.weekday())
    end = start + timedelta(days=6)
    goals = db.scalars(select(StudyGoal).where(StudyGoal.user_id == user.id).order_by(StudyGoal.id)).all()
    rows = db.execute(select(StudyTask, Content.title, StudyGoal.name)
        .join(Content, Content.id == StudyTask.content_id).join(StudyGoal, StudyGoal.id == StudyTask.goal_id)
        .where(StudyTask.user_id == user.id, StudyTask.day.between(start, end))
        .order_by(StudyTask.day, StudyTask.priority, StudyTask.id))
    tasks = [dict(task_out(task), title=title, goal_name=name) for task, title, name in rows]
    budget = db.get(WeekBudget, (user.id, start))
    return {"week": start, "end": end, "today": today, "budget": budget.minutes if budget else None,
            "goals": [{"id": goal.id, "name": goal.name} for goal in goals],
            "tasks": tasks, "summary": summarize(tasks)}


@router.post("/goals")
def create_goal(data: GoalInput, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    goal = db.scalar(select(StudyGoal).where(StudyGoal.user_id == user.id, func.lower(StudyGoal.name) == func.lower(data.name)))
    if goal is None:
        if db.scalar(select(func.count()).select_from(StudyGoal).where(StudyGoal.user_id == user.id)) >= 100:
            raise HTTPException(409, {"code": "goal_limit"})
        goal = StudyGoal(user_id=user.id, name=data.name)
        db.add(goal)
        db.commit()
    return {"id": goal.id, "name": goal.name}


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: ContentId, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    db.delete(owned(db, StudyGoal, user.id, goal_id))
    db.commit()
    return Response(status_code=204)


@router.put("/weeks/{week}/budget", status_code=204)
def set_budget(week: PlanDay, data: BudgetInput, db: DbSession, user: CurrentUser):
    if week.weekday() != 0:
        raise HTTPException(422, "Expected Monday")
    lock_owner(db, user)
    entry = db.get(WeekBudget, (user.id, week))
    if entry and entry.minutes == data.minutes:
        return Response(status_code=204)
    if (entry.minutes if entry else None) != data.previous:
        raise HTTPException(412, "Budget changed")
    if entry:
        entry.minutes = data.minutes
    else:
        db.add(WeekBudget(user_id=user.id, week=week, minutes=data.minutes))
    db.commit()
    return Response(status_code=204)


@router.post("/tasks")
def create_task(data: TaskInput, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    owned(db, StudyGoal, user.id, data.goal_id)
    get_own_content(db, user, data.content_id, lock=True)
    existing = db.scalar(select(StudyTask).where(StudyTask.goal_id == data.goal_id, StudyTask.content_id == data.content_id))
    if existing:
        if any(getattr(existing, key) != getattr(data, key) for key in ("day", "minutes", "priority")):
            raise HTTPException(409, {"code": "already_planned"})
        return task_out(existing)
    task = StudyTask(user_id=user.id, **data.model_dump())
    db.add(task)
    db.flush()
    record(db, task, "created")
    db.commit()
    return task_out(task)


@router.put("/tasks/{task_id}/day")
def move(task_id: ContentId, data: MoveInput, db: DbSession, user: CurrentUser, version: Version):
    task = owned(db, StudyTask, user.id, task_id)
    if task.day != data.day:
        matches(task, version)
        if task.completed_at:
            raise HTTPException(409, {"code": "task_completed"})
        task.day = data.day
        task.version += 1
        record(db, task, "moved")
        db.commit()
    return task_out(task)


@router.put("/tasks/{task_id}/complete")
def complete(task_id: ContentId, db: DbSession, user: CurrentUser, version: Version):
    task = owned(db, StudyTask, user.id, task_id)
    if task.completed_at is None:
        matches(task, version)
        task.completed_at = datetime.now(timezone.utc)
        task.version += 1
        record(db, task, "completed")
        db.commit()
    return task_out(task)


@router.delete("/tasks/{task_id}", status_code=204)
def remove(task_id: ContentId, db: DbSession, user: CurrentUser, version: Version):
    task = owned(db, StudyTask, user.id, task_id)
    matches(task, version)
    db.delete(task)
    db.commit()
    return Response(status_code=204)
