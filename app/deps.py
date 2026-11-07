import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.schemas import MAX_BIGINT
from app.sessions import find_user_by_token
from app.telegram_auth import USERNAME_RE

MIN_BOT_KEY_LENGTH = 32

TelegramId = Annotated[int | None, Header(gt=0, le=MAX_BIGINT)]


def get_db() -> Iterator[Session]:
    """Одна сессия БД на один запрос; закрывается автоматически."""
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


def _bot_key_valid(provided: str) -> bool:
    expected = settings.bot_api_key
    if len(expected) < MIN_BOT_KEY_LENGTH:
        return False  # ключ не задан или слишком короткий: вход ботом отключён
    return hmac.compare_digest(provided.encode(), expected.encode())


def _bearer_token(header_value: str) -> str | None:
    """Токен из «Bearer <токен>» или None, если формат другой."""
    scheme, _, token = header_value.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_or_create_user(
    db: Session, telegram_id: int, username: str | None = None
) -> User:
    query = select(User).where(User.telegram_id == telegram_id)
    user = db.scalar(query)
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Два запроса одновременно создали одного пользователя
            db.rollback()
            user = db.scalar(query)
    return user


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header(max_length=512)] = None,
    x_bot_key: Annotated[str | None, Header(max_length=256)] = None,
    x_telegram_id: TelegramId = None,
    x_telegram_username: Annotated[str | None, Header(max_length=64)] = None,
    x_dev_telegram_id: TelegramId = None,
) -> User:
    """Определяет, кто делает запрос.

    1. Mini App: Authorization: Bearer <токен сессии>.
    2. Бот: X-Bot-Key + X-Telegram-Id (+ X-Telegram-Username).
    3. ВРЕМЕННО для разработки: X-Dev-Telegram-Id при DEV_AUTH_ENABLED
       (будет удалён в шаге 5.5).

    Если указан Authorization или X-Bot-Key, это единственный способ входа:
    при неудаче сразу 401, без перехода к другим способам.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
    )

    if authorization is not None:
        # Два способа входа в одном запросе: отказываем
        if x_bot_key is not None or x_dev_telegram_id is not None:
            raise unauthorized
        token = _bearer_token(authorization)
        user = find_user_by_token(db, token) if token else None
        if user is None:
            raise unauthorized
        return user

    if x_bot_key is not None:
        if x_telegram_id is None or not _bot_key_valid(x_bot_key):
            raise unauthorized
        username = (
            x_telegram_username
            if x_telegram_username and USERNAME_RE.fullmatch(x_telegram_username)
            else None
        )
        user = get_or_create_user(db, x_telegram_id, username)
        if user.username != username:
            user.username = username
            db.commit()
        return user

    if settings.dev_auth_enabled and x_dev_telegram_id is not None:
        return get_or_create_user(db, x_dev_telegram_id)

    raise unauthorized


CurrentUser = Annotated[User, Depends(get_current_user)]