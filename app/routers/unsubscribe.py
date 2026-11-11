from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.csrf import require_same_origin
from app.deps import DbSession
from app.models import User
from app.schemas import UnsubscribeRequest
from app.unsubscribe import SecretKeyMissing, verify_token

router = APIRouter(prefix="/auth/unsubscribe", tags=["auth"])


def apply_unsubscribe(db: Session, token: str) -> None:
    """Отключает напоминания пользователя по подписанному токену. Повтор безвреден."""
    try:
        user_id = verify_token(token)
    except SecretKeyMissing:
        # Ошибка настройки сервера, а не чужая попытка
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Unsubscribe is temporarily unavailable"
        )
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid token")
    # Одна команда без загрузки пользователя; удалённый пользователь не ошибка
    db.execute(update(User).where(User.id == user_id).values(reminders_enabled=False))
    db.commit()


def no_content() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def unsubscribe_from_page(data: UnsubscribeRequest, db: DbSession):
    """Для страницы unsubscribe.html: токен в теле, проверка Origin."""
    apply_unsubscribe(db, data.token)
    return no_content()


@router.post("/one-click", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe_one_click(
    db: DbSession, token: Annotated[str, Query(max_length=128)]
):
    """RFC 8058: почтовый сервис шлёт POST (тело List-Unsubscribe=One-Click) на адрес
    из заголовка List-Unsubscribe. Origin у такого запроса нет, и проверять его
    нельзя. Это безопасно: cookie не используется, действует только подписанный
    токен, GET ничего не делает (405)."""
    apply_unsubscribe(db, token)
    return no_content()