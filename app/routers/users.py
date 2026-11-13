from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.deps import CurrentUser, DbSession
from app.export import build_export
from app.ratelimit import EXPORT_USER, check_limits, make_key, record
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


@router.get("/me/export")
def export_me(db: DbSession, user: CurrentUser):
    """Все данные пользователя одним JSON-файлом (без хэша пароля и сессий).
    Сборка идёт в памяти, поэтому число запросов ограничено."""
    key = make_key(str(user.id))
    check_limits(db, (EXPORT_USER, key))
    record(db, EXPORT_USER, key)
    return JSONResponse(
        build_export(db, user),
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="teleiosis-export.json"',
        },
    )