import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import delete, or_, select

from app.config import settings
from app.cookies import clear_session_cookie
from app.csrf import require_same_origin
from app.deps import DbSession
from app.mailer import send_password_reset
from app.models import AuthSession, PasswordResetToken, User
from app.passwords import hash_password
from app.ratelimit import (
    RESET_EMAIL,
    RESET_IP,
    check_limits,
    client_ip,
    make_key,
    record,
)
from app.schemas import PasswordResetConfirm, PasswordResetRequest
from app.sessions import TOKEN_RE, hash_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/password-reset", tags=["auth"])

RESET_TOKEN_LIFETIME = timedelta(hours=1)
NEUTRAL_MESSAGE = "If the address is registered, a reset link has been sent."


def issue_reset_token(db: DbSession, user: User) -> str:
    """Создаёт токен. Прежние токены пользователя и все просроченные удаляются."""
    now = datetime.now(timezone.utc)
    db.execute(
        delete(PasswordResetToken).where(
            or_(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.expires_at <= now,
            )
        )
    )
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + RESET_TOKEN_LIFETIME,
        )
    )
    db.commit()
    return token


def reset_link(token: str) -> str:
    # Токен во фрагменте: он не уходит на сервер, в логи и в заголовок Referer
    return f"{settings.app_origin}/app/reset.html#token={token}"


@router.post(
    "/request",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_same_origin)],
)
def request_reset(
    data: PasswordResetRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: DbSession,
):
    # Лимиты считаются по введённому адресу, а не по наличию аккаунта
    email_key = make_key(data.email)
    ip_key = make_key(client_ip(request))
    check_limits(db, (RESET_EMAIL, email_key), (RESET_IP, ip_key))
    record(db, RESET_EMAIL, email_key)
    record(db, RESET_IP, ip_key)

    user = db.scalar(select(User).where(User.email == data.email))
    if user is not None:
        token = issue_reset_token(db, user)
        # Письмо уходит после ответа: время ответа не выдаёт, есть ли аккаунт
        background_tasks.add_task(send_password_reset, data.email, reset_link(token))

    response.headers["Cache-Control"] = "no-store"
    return {"detail": NEUTRAL_MESSAGE}


@router.post(
    "/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def confirm_reset(data: PasswordResetConfirm, db: DbSession):
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")
    if not TOKEN_RE.fullmatch(data.token):
        raise invalid

    now = datetime.now(timezone.utc)
    # Удаление и проверка одной командой: два запроса с одним токеном не пройдут оба
    user_id = db.execute(
        delete(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == hash_token(data.token),
            PasswordResetToken.expires_at > now,
        )
        .returning(PasswordResetToken.user_id)
    ).scalar_one_or_none()
    if user_id is None:
        raise invalid
    user = db.get(User, user_id)
    if user is None:
        raise invalid

    user.password_hash = hash_password(data.password)
    if user.email_verified_at is None:
        user.email_verified_at = now  # человек доказал доступ к почте
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return response