from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, StringConstraints, field_validator
from sqlalchemy import and_, delete, func, select

from app.deps import CurrentUser, DbSession
from app.duration import estimated_minutes
from app.learning_events import record_learning_event
from app.models import Content, StudyGoal, StudyGoalMaterial
from app.routers.contents import ContentId, SORT_ORDER, get_own_content
from app.routers.organization import lock_owner
from app.routers.week_plan import GOAL_LIMIT, GoalInput, ObjectId, Version, Write, link_goal_material, matches, owned
from app.schemas import MAX_BIGINT

router = APIRouter(prefix="/mobile/learning/goals", tags=["learning"])
GoalStatus = Literal["active", "completed", "archived"]
Limit = Annotated[int, Query(ge=1, le=50)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]
Result = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000, pattern=r"^[^\x00]*$")]


class CreateGoal(GoalInput):
    result: Result | None = None

    @field_validator("result")
    @classmethod
    def normalize_result(cls, value: str | None) -> str | None:
        return value or None


class UpdateGoal(CreateGoal):
    status: GoalStatus


class AddMaterial(Write):
    content_id: ObjectId


class GoalOut(BaseModel):
    id: int
    name: str
    result: str | None
    status: GoalStatus
    version: int
    materials_total: int
    materials_studied: int
    linked: bool | None = None


class GoalPage(BaseModel):
    items: list[GoalOut]
    total: int


class GoalMaterialOut(BaseModel):
    id: int
    title: str
    status: str


class GoalMaterialPage(BaseModel):
    items: list[GoalMaterialOut]
    total: int


class GoalDetailOut(GoalOut):
    next_material: GoalMaterialOut | None


class GoalCandidate(GoalMaterialOut):
    content_type: str
    duration_minutes: int | None
    linked: bool


class GoalCandidatePage(BaseModel):
    items: list[GoalCandidate]
    total: int


def goal_membership(user_id: int, goal_id: int):
    return select(StudyGoalMaterial.content_id).where(
        StudyGoalMaterial.goal_id == goal_id, StudyGoalMaterial.user_id == user_id,
        StudyGoalMaterial.content_id == Content.id,
    ).exists()


def goal_query(user_id: int, content_id: int | None = None):
    memberships = select(
        StudyGoalMaterial.goal_id,
        func.count().filter(Content.status != "irrelevant").label("materials_total"),
        func.count().filter(Content.status == "studied").label("materials_studied"),
    ).join(Content, and_(Content.id == StudyGoalMaterial.content_id, Content.user_id == StudyGoalMaterial.user_id)).where(
        StudyGoalMaterial.user_id == user_id,
    ).group_by(StudyGoalMaterial.goal_id).subquery()
    linked = select(StudyGoalMaterial.goal_id).where(
        StudyGoalMaterial.goal_id == StudyGoal.id, StudyGoalMaterial.user_id == user_id,
        StudyGoalMaterial.content_id == content_id,
    ).exists().label("linked")
    return select(
        StudyGoal.id, StudyGoal.name, StudyGoal.result, StudyGoal.status, StudyGoal.version,
        func.coalesce(memberships.c.materials_total, 0).label("materials_total"),
        func.coalesce(memberships.c.materials_studied, 0).label("materials_studied"),
        *([linked] if content_id is not None else []),
    ).outerjoin(memberships, memberships.c.goal_id == StudyGoal.id).where(StudyGoal.user_id == user_id)


def get_goal(db: DbSession, user_id: int, goal_id: int):
    row = db.execute(goal_query(user_id).where(StudyGoal.id == goal_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Goal not found")
    return row


@router.get("", response_model=GoalPage)
def list_goals(db: DbSession, user: CurrentUser, status: GoalStatus | None = None,
               content_id: Annotated[int, Query(gt=0, le=MAX_BIGINT)] | None = None, limit: Limit = 20, offset: Offset = 0):
    if content_id is not None:
        get_own_content(db, user, content_id)
    filters = [StudyGoal.user_id == user.id]
    if status is not None:
        filters.append(StudyGoal.status == status)
    rows = db.execute(goal_query(user.id, content_id).where(*filters)
                      .order_by(StudyGoal.id).limit(limit).offset(offset)).mappings().all()
    return {"items": rows, "total": db.scalar(select(func.count()).select_from(StudyGoal).where(*filters))}


@router.get("/{goal_id}", response_model=GoalDetailOut)
def read_goal(goal_id: ContentId, db: DbSession, user: CurrentUser):
    goal = get_goal(db, user.id, goal_id)
    next_material = db.execute(select(Content.id, Content.title, Content.status)
        .where(Content.user_id == user.id, Content.status.in_(("unseen", "planned")), goal_membership(user.id, goal_id))
        .order_by(Content.status != "planned", *SORT_ORDER["oldest"]).limit(1)).mappings().first()
    return dict(goal, next_material=next_material)


@router.post("", response_model=GoalOut)
def create_goal(data: CreateGoal, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    goal = db.scalar(select(StudyGoal).where(StudyGoal.user_id == user.id, func.lower(StudyGoal.name) == func.lower(data.name)))
    if goal is None:
        if db.scalar(select(func.count()).select_from(StudyGoal).where(StudyGoal.user_id == user.id)) >= GOAL_LIMIT:
            raise HTTPException(409, {"code": "goal_limit"})
        goal = StudyGoal(user_id=user.id, name=data.name, result=data.result)
        db.add(goal)
        db.flush()
        record_learning_event(db, user, "goal_created", goal.id)
    elif goal.result != data.result:
        raise HTTPException(409, {"code": "goal_name_taken"})
    result = get_goal(db, user.id, goal.id)
    db.commit()
    return result


@router.put("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: ContentId, data: UpdateGoal, version: Version, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    goal = owned(db, StudyGoal, user.id, goal_id)
    values = data.model_dump()
    if any(getattr(goal, key) != value for key, value in values.items()):
        matches(goal, version)
        duplicate = select(StudyGoal.id).where(
            StudyGoal.user_id == user.id, StudyGoal.id != goal.id, func.lower(StudyGoal.name) == func.lower(data.name),
        ).exists()
        if db.scalar(select(duplicate)):
            raise HTTPException(409, {"code": "goal_name_taken"})
        for key, value in values.items():
            setattr(goal, key, value)
        goal.version += 1
        db.flush()
    result = get_goal(db, user.id, goal.id)
    db.commit()
    return result


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: ContentId, version: Version, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    goal = owned(db, StudyGoal, user.id, goal_id)
    matches(goal, version)
    db.delete(goal)
    db.commit()
    return Response(status_code=204)


@router.get("/{goal_id}/materials", response_model=GoalMaterialPage)
def list_materials(goal_id: ContentId, db: DbSession, user: CurrentUser, limit: Limit = 20, offset: Offset = 0):
    get_goal(db, user.id, goal_id)
    filters = (StudyGoalMaterial.goal_id == goal_id, StudyGoalMaterial.user_id == user.id)
    rows = db.execute(select(Content.id, Content.title, Content.status)
        .join(StudyGoalMaterial, and_(StudyGoalMaterial.content_id == Content.id, StudyGoalMaterial.user_id == Content.user_id))
        .where(*filters).order_by(Content.id).limit(limit).offset(offset)).mappings().all()
    return {"items": rows, "total": db.scalar(select(func.count()).select_from(StudyGoalMaterial).where(*filters))}


@router.post("/{goal_id}/materials", status_code=204)
def add_material(goal_id: ContentId, data: AddMaterial, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    owned(db, StudyGoal, user.id, goal_id)
    get_own_content(db, user, data.content_id, lock=True)
    link_goal_material(db, user, goal_id, data.content_id)
    db.commit()
    return Response(status_code=204)


@router.get("/{goal_id}/candidates", response_model=GoalCandidatePage)
def list_candidates(
    goal_id: ContentId, db: DbSession, user: CurrentUser,
    q: Annotated[str, Query(max_length=100)] = "", limit: Limit = 20, offset: Offset = 0,
):
    if db.scalar(select(StudyGoal.id).where(StudyGoal.id == goal_id, StudyGoal.user_id == user.id)) is None:
        raise HTTPException(404, "Goal not found")
    filters = [Content.user_id == user.id]
    if q.strip():
        filters.append(Content.title.icontains(q.strip(), autoescape=True))
    rows = db.execute(select(Content, goal_membership(user.id, goal_id).label("linked"))
        .where(*filters).order_by(*SORT_ORDER["newest"]).limit(limit).offset(offset))
    return {
        "items": [{"id": material.id, "title": material.title, "status": material.status,
                   "content_type": material.content_type, "duration_minutes": estimated_minutes(material), "linked": linked}
                  for material, linked in rows],
        "total": db.scalar(select(func.count()).select_from(Content).where(*filters)),
    }


@router.delete("/{goal_id}/materials/{content_id}", status_code=204)
def remove_material(goal_id: ContentId, content_id: ContentId, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    owned(db, StudyGoal, user.id, goal_id)
    get_own_content(db, user, content_id, lock=True)
    db.execute(delete(StudyGoalMaterial).where(
        StudyGoalMaterial.goal_id == goal_id, StudyGoalMaterial.content_id == content_id,
        StudyGoalMaterial.user_id == user.id,
    ))
    db.commit()
    return Response(status_code=204)
