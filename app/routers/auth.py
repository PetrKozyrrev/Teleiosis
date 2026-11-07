import logging

from fastapi import APIRouter, HTTPException, Response, status

from app.config import settings
from app.deps import DbSession, _get_or_create_user
from app.schemas import AuthRequest, AuthResponse
from app.sessions import create_session
from app.telegram_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=AuthResponse)
def login_with_telegram(data: AuthRequest, response: Response, db: DbSession):
    if not settings.bot_token:
        # Ошибка настройки сервера, а не чужая попытка входа
        logger.error("BOT_TOKEN is not configured: Mini App login is unavailable")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Login is temporarily unavailable"
        )

    try:
        verified = validate_init_data(data.init_data, settings.bot_token)
    except InitDataError as exc:
        # В лог только короткая причина: без initData и без токена
        logger.warning("initData rejected: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    user = _get_or_create_user(db, verified.telegram_id, verified.username)
    if user.username != verified.username:
        user.username = verified.username
        db.commit()

    token, expires_at = create_session(db, user)
    response.headers["Cache-Control"] = "no-store"
    return {"token": token, "expires_at": expires_at, "user": user}