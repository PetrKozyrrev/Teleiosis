from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.schemas import SettingsUpdate, UserOut

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser):
    return user


@router.patch("/me/settings", response_model=UserOut)
def update_settings(data: SettingsUpdate, db: DbSession, user: CurrentUser):
    """Меняет только присланные поля. Проверки уже сделала схема, поэтому
    при отказе (422) ничего не изменяется."""
    changes = data.model_fields_set
    if "timezone" in changes:
        user.timezone = data.timezone
    if "reminders_enabled" in changes:
        user.reminders_enabled = data.reminders_enabled
    if "reminder_time" in changes:
        user.reminder_time = data.reminder_time
    db.commit()
    db.refresh(user)
    return user