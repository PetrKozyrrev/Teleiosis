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
from sqlalchemy import delete, or_

from app.config import settings
from app.csrf import require_same_origin
from app.deps import CurrentUser, DbSession
from app.mailer import send_email_verification
from app.models import EmailVerificationToken, User
from app.ratelimit import (
    VERIFY_IP,
    VERIFY_USER,
    check_limits,
    client_ip,
    make_key,
    record,
)
from app.schemas import EmailVerificationConfirm
from app.sessions import TOKEN_RE, hash_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/email-verification", tags=["auth"])

VERIFY_TOKEN_LIFETIME = timedelta(hours=24)


def issue_verification_token(db: DbSession, user: User) -> str:
    """Создаёт токен. Прежние токены пользователя и все просроченные удаляются."""
    now = datetime.now(timezone.utc)
    db.execute(
        delete(EmailVerificationToken).where(
            or_(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.expires_at <= now,
            )
        )
    )
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + VERIFY_TOKEN_LIFETIME,
        )
    )
    db.commit()
    return token


def verification_link(token: str) -> str:
    # Токен во фрагменте: он не уходит на сервер, в логи и в заголовок Referer
    return f"{settings.app_origin}/app/verify.html#token={token}"


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
def request_verification(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
):
    if user.email is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account has no e-mail address")
    if user.email_verified_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail is already verified")

    user_key = make_key(str(user.id))
    ip_key = make_key(client_ip(request))
    check_limits(db, (VERIFY_USER, user_key), (VERIFY_IP, ip_key))
    record(db, VERIFY_USER, user_key)
    record(db, VERIFY_IP, ip_key)

    token = issue_verification_token(db, user)
    # Письмо уходит после ответа: сбой почты не ломает запрос
    background_tasks.add_task(
        send_email_verification, user.email, verification_link(token)
    )

    response.headers["Cache-Control"] = "no-store"
    return {"detail": "Verification link has been sent."}


@router.post(
    "/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def confirm_verification(data: EmailVerificationConfirm, db: DbSession):
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")
    if not TOKEN_RE.fullmatch(data.token):
        raise invalid

    now = datetime.now(timezone.utc)
    # Удаление и проверка одной командой: два запроса с одним токеном не пройдут оба
    user_id = db.execute(
        delete(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_hash == hash_token(data.token),
            EmailVerificationToken.expires_at > now,
        )
        .returning(EmailVerificationToken.user_id)
    ).scalar_one_or_none()
    if user_id is None:
        raise invalid
    user = db.get(User, user_id)
    if user is None:
        raise invalid

    if user.email_verified_at is None:
        user.email_verified_at = now
    db.execute(
        delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
    )
    db.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Cache-Control"] = "no-store"
    return response