from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.cookies import cookie_name
from app.csrf import check_same_origin
from app.db import SessionLocal
from app.models import User
from app.sessions import find_user_by_token


def get_db() -> Iterator[Session]:
    """Одна сессия БД на один запрос; закрывается автоматически."""
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> User:
    """Сессия сайта после входа по e-mail. Изменяющие запросы проверяют Origin."""
    token = request.cookies.get(cookie_name())
    authorization = request.headers.get("authorization")
    if authorization is not None:
        if token is not None:
            # Preserve cookie CSRF rejection before refusing mixed credentials.
            check_same_origin(request)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Mixed credentials")
        parts = authorization.split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            user = find_user_by_token(db, parts[1], client_type="mobile")
            if user is not None:
                return user
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if token is not None:
        check_same_origin(request)
        user = find_user_by_token(db, token)
        if user is not None:
            return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


CurrentUser = Annotated[User, Depends(get_current_user)]
