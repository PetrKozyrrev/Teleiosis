from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import User


def get_db() -> Iterator[Session]:
    """Одна сессия БД на один запрос; закрывается автоматически."""
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    x_dev_telegram_id: Annotated[int | None, Header(gt=0)] = None,
) -> User:
    """ВРЕМЕННАЯ идентификация для разработки (заменим на этапе 5
    проверкой подписи Telegram initData)."""
    if not settings.dev_auth_enabled or x_dev_telegram_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    query = select(User).where(User.telegram_id == x_dev_telegram_id)
    user = db.scalar(query)
    if user is None:
        user = User(telegram_id=x_dev_telegram_id)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Два запроса одновременно создали одного пользователя
            db.rollback()
            user = db.scalar(query)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]