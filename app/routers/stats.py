from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.deps import CurrentUser, DbSession
from app.schemas import StatsOut
from app.stats import ReadingPeriod, compute_stats, reading_progress

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsOut)
def read_stats(response: Response, db: DbSession, user: CurrentUser):
    # Личные данные: не кэшируем
    response.headers["Cache-Control"] = "no-store"
    return compute_stats(db, user)


@router.get("/mobile/reading-progress")
def read_reading_progress(response: Response, db: DbSession, user: CurrentUser, period: ReadingPeriod = "week",
                          offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0):
    response.headers["Cache-Control"] = "no-store"
    return reading_progress(db, user, period, offset)
