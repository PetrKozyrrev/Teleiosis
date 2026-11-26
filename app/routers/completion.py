from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import and_, select

from app.activity import record_activity
from app.deps import CurrentUser, DbSession
from app.learning_events import record_learning_event
from app.models import ContentReflection, LearningCompletion, StudyGoal, StudyTask
from app.routers.contents import ContentId, apply_content_status, get_own_content
from app.routers.organization import lock_owner
from app.routers.review import OperationKey
from app.routers.week_plan import ObjectId, Write, finish_task
from app.schemas import ContentOut

router = APIRouter(prefix="/mobile/learning/materials", tags=["learning"])
ContentVersion = Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]{0,18}"$')]


class CompletionInput(Write):
    task_id: ObjectId | None = None


class ReflectionInput(Write):
    thought: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000, pattern=r"^[^\x00]*$")]
    previous: ObjectId | None


class ReflectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    thought: str
    version: int


class OpenTask(BaseModel):
    id: int
    day: date
    goal_name: str


class CompletionContext(BaseModel):
    material: ContentOut
    tasks: list[OpenTask]
    reflection: ReflectionOut | None


class CompletionOut(BaseModel):
    material: ContentOut
    task_completed: bool


@router.get("/{content_id}/completion", response_model=CompletionContext)
def read_completion(content_id: ContentId, db: DbSession, user: CurrentUser):
    material = get_own_content(db, user, content_id)
    tasks = db.execute(
        select(StudyTask.id, StudyTask.day, StudyGoal.name.label("goal_name")).join(
            StudyGoal, and_(StudyGoal.id == StudyTask.goal_id, StudyGoal.user_id == StudyTask.user_id),
        ).where(StudyTask.user_id == user.id, StudyTask.content_id == content_id,
                StudyTask.completed_at.is_(None), StudyGoal.status == "active")
        .order_by(StudyTask.day, StudyTask.priority, StudyTask.id)
    ).mappings().all()
    reflection = db.get(ContentReflection, content_id)
    return {"material": material, "tasks": tasks, "reflection": reflection}


@router.post("/{content_id}/completion", response_model=CompletionOut)
def complete_material(content_id: ContentId, data: CompletionInput, key: OperationKey,
                      version: ContentVersion, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    material = get_own_content(db, user, content_id, lock=True)
    receipt = db.get(LearningCompletion, (user.id, key))
    if receipt is not None and (receipt.content_id, receipt.task_id) != (content_id, data.task_id):
        raise HTTPException(409, {"code": "completion_key_reused"})

    task = None
    if data.task_id is not None:
        task = db.scalar(select(StudyTask).where(
            StudyTask.id == data.task_id, StudyTask.user_id == user.id, StudyTask.content_id == content_id,
        ).with_for_update())
        if task is None and receipt is None:
            raise HTTPException(404, {"code": "completion_task_missing"})
    if receipt is not None:
        return CompletionOut(material=ContentOut.model_validate(material), task_completed=bool(task and task.completed_at))
    if int(version[1:-1]) != material.version:
        raise HTTPException(412, {"code": "content_version_changed"})

    now = datetime.now(timezone.utc)
    if apply_content_status(material, "studied", now):
        record_learning_event(db, user, "material_studied", material.id, material_id=material.id, now=now)
    if task is not None:
        finish_task(db, task, now)
    db.add(LearningCompletion(user_id=user.id, key=key, content_id=content_id, task_id=data.task_id))
    db.flush()
    db.refresh(material)
    result = CompletionOut(material=ContentOut.model_validate(material), task_completed=task is not None)
    db.commit()
    record_activity(db, user, now)
    return result


@router.put("/{content_id}/reflection", response_model=ReflectionOut)
def save_reflection(content_id: ContentId, data: ReflectionInput, db: DbSession, user: CurrentUser):
    get_own_content(db, user, content_id, lock=True)
    reflection = db.get(ContentReflection, content_id)
    if reflection is not None and reflection.thought == data.thought:
        return ReflectionOut.model_validate(reflection)
    if (reflection.version if reflection else None) != data.previous:
        raise HTTPException(412, {"code": "reflection_version_changed"})
    if reflection is None:
        reflection = ContentReflection(content_id=content_id, user_id=user.id, thought=data.thought)
        db.add(reflection)
    else:
        reflection.thought = data.thought
        reflection.version += 1
    db.flush()
    result = ReflectionOut.model_validate(reflection)
    record_learning_event(db, user, "study_reflection_saved", f"{content_id}:{reflection.version}", material_id=content_id)
    db.commit()
    return result
