from fastapi import APIRouter, Response

from app.deps import CurrentUser, DbSession
from app.schemas import StatsOut
from app.stats import compute_stats

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsOut)
def read_stats(response: Response, db: DbSession, user: CurrentUser):
    # Личные данные: не кэшируем
    response.headers["Cache-Control"] = "no-store"
    return compute_stats(db, user)