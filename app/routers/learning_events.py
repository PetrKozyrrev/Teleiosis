from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import model_validator

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.learning_events import ClientEventName, record_learning_event
from app.routers.contents import get_own_content
from app.routers.review import OperationKey
from app.routers.week_plan import ObjectId, Write

router = APIRouter(prefix="/mobile/learning/events", tags=["learning"])
OPEN_EVENTS = {"saved_material_reopened", "next_action_opened", "recommendation_opened"}
BUDGET_EVENTS = {"time_budget_selected", "recommendation_opened"}


class ClientEvent(Write):
    name: ClientEventName
    visit_id: UUID
    material_id: ObjectId | None = None
    budget_minutes: Literal[5, 15, 30, 60] | None = None
    has_results: bool | None = None

    @model_validator(mode="after")
    def valid_fields(self):
        if (self.material_id is not None) != (self.name in OPEN_EVENTS):
            raise ValueError("Material field must match the event")
        if (self.budget_minutes is not None) != (self.name in BUDGET_EVENTS):
            raise ValueError("Budget field must match the event")
        if (self.has_results is not None) != (self.name == "time_budget_selected"):
            raise ValueError("Results field must match the event")
        return self


@router.post("", status_code=204)
def ingest(data: ClientEvent, key: OperationKey, db: DbSession, user: CurrentUser):
    if settings.learning_metrics_enabled:
        if data.material_id is not None:
            get_own_content(db, user, data.material_id)
        record_learning_event(
            db, user, data.name, key, material_id=data.material_id, visit_id=data.visit_id,
            budget_minutes=data.budget_minutes, has_results=data.has_results,
        )
        db.commit()
    return Response(status_code=204)
