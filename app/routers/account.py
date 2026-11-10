from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete

from app.cookies import cookie_name
from app.deps import CurrentUser, DbSession
from app.models import AuthSession, PasswordResetToken
from app.passwords import hash_password, verify_password
from app.ratelimit import PASSWORD_USER, check_limits, clear, make_key, record
from app.schemas import ChangePasswordRequest
from app.sessions import hash_token

router = APIRouter(prefix="/auth", tags=["auth"])


def current_token(request: Request) -> str | None:
    """Токен сессии этого запроса: cookie сайта или Bearer. Источник один:
    get_current_user уже отказал бы, если бы их было два."""
    token = request.cookies.get(cookie_name())
    if token is None:
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
    return token


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: ChangePasswordRequest, request: Request, db: DbSession, user: CurrentUser
):
    if user.password_hash is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account has no password")

    # Лимит проверяется до хэширования: заблокированный запрос ничего не стоит.
    # Неверный пароль не 401: сайт принял бы это за окончание сессии.
    user_key = make_key(str(user.id))
    check_limits(db, (PASSWORD_USER, user_key))
    if not verify_password(data.current_password, user.password_hash):
        record(db, PASSWORD_USER, user_key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")

    user.password_hash = hash_password(data.new_password)

    # Все остальные сессии закрываются, текущая остаётся
    token = current_token(request)
    keep_hash = hash_token(token) if token else None
    query = delete(AuthSession).where(AuthSession.user_id == user.id)
    if keep_hash is not None:
        query = query.where(AuthSession.token_hash != keep_hash)
    db.execute(query)
    # Ссылки сброса пароля, отправленные до смены, больше не нужны
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.commit()
    clear(db, PASSWORD_USER, user_key)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Cache-Control"] = "no-store"
    return response