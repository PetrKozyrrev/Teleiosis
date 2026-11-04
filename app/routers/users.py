from fastapi import APIRouter

from app.deps import CurrentUser
from app.schemas import UserOut

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser):
    return user