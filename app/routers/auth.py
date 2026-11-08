import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import DbSession, get_or_create_user
from app.models import User
from app.passwords import hash_password
from app.schemas import AuthRequest, AuthResponse, RegisterRequest, UserOut
from app.sessions import create_session
from app.telegram_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Версия текста согласия на обработку персональных данных.
# Заменить версией утверждённого юристом текста до публичного запуска.
CONSENT_VERSION = "draft-1"


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

    user = get_or_create_user(db, verified.telegram_id, verified.username)
    if user.username != verified.username:
        user.username = verified.username
        db.commit()

    token, expires_at = create_session(db, user)
    response.headers["Cache-Control"] = "no-store"
    return {"token": token, "expires_at": expires_at, "user": user}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, response: Response, db: DbSession):
    # Хэшируем до обращения к БД: время ответа не зависит от того, занят ли адрес
    password_hash = hash_password(data.password)
    user = User(
        email=data.email,
        password_hash=password_hash,
        consent_at=datetime.now(timezone.utc),
        consent_version=CONSENT_VERSION,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Занятый e-mail ловит ограничение БД (нет гонки «проверить, потом вставить»)
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    db.refresh(user)
    response.headers["Cache-Control"] = "no-store"
    return user