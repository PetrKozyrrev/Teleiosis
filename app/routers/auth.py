import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.cookies import clear_session_cookie, cookie_name, set_session_cookie
from app.csrf import require_same_origin
from app.deps import DbSession, get_or_create_user
from app.emails import normalize_email
from app.models import User
from app.passwords import hash_password, needs_rehash, verify_dummy, verify_password
from app.ratelimit import (
    LOGIN_EMAIL_IP,
    LOGIN_IP,
    REGISTER_IP,
    check_limits,
    clear,
    client_ip,
    make_key,
    record,
)
from app.schemas import (
    AuthRequest,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserOut,
)
from app.sessions import create_session, delete_session
from app.telegram_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Версия текста согласия на обработку персональных данных.
# Заменить версией утверждённого юристом текста до публичного запуска.
CONSENT_VERSION = "draft-1"


def invalid_login() -> HTTPException:
    # Одно сообщение для неверного пароля и несуществующего e-mail
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

def login_failed(db: DbSession, ip_key: str, pair_key: str) -> HTTPException:
    """Записывает неудачную попытку в оба счётчика и возвращает общую ошибку входа."""
    record(db, LOGIN_IP, ip_key)
    record(db, LOGIN_EMAIL_IP, pair_key)
    return invalid_login()


def start_session(request: Request, response: Response, db: DbSession, user: User) -> None:
    """Новая сессия для браузера. Сессия из прежней cookie (если была) удаляется."""
    old_token = request.cookies.get(cookie_name())
    if old_token:
        delete_session(db, old_token)
    token, _ = create_session(db, user)
    set_session_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"


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


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def register(data: RegisterRequest, request: Request, response: Response, db: DbSession):
    # Лимит проверяется до хэширования: заблокированный запрос ничего не стоит.
    # Считаются все попытки, дошедшие до этого места (ошибки формата не считаются).
    ip_key = make_key(client_ip(request))
    check_limits(db, (REGISTER_IP, ip_key))
    record(db, REGISTER_IP, ip_key)

    # Хэшируем до обращения к БД: время ответа не зависит от того, занят ли адрес
    password_hash = hash_password(data.password)
    # Пояс передаём только если он известен: иначе работает значение БД (UTC)
    extra = {"timezone": data.timezone} if data.timezone else {}
    user = User(
        email=data.email,
        password_hash=password_hash,
        consent_at=datetime.now(timezone.utc),
        consent_version=CONSENT_VERSION,
        **extra,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Занятый e-mail ловит ограничение БД (нет гонки «проверить, потом вставить»)
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    db.refresh(user)
    start_session(request, response, db, user)
    return user


@router.post(
    "/login",
    response_model=UserOut,
    dependencies=[Depends(require_same_origin)],
)
def login(data: LoginRequest, request: Request, response: Response, db: DbSession):
    try:
        email = normalize_email(data.email)
    except ValueError:
        email = None  # такого аккаунта быть не может: ответ как для неверного пароля

    # Лимит проверяется до любой работы с паролем. Ключ строится от введённой
    # строки, а не от наличия аккаунта: ответ 429 не выдаёт, есть ли такой e-mail.
    ip = client_ip(request)
    ip_key = make_key(ip)
    pair_key = make_key(email or data.email.strip().lower(), ip)
    check_limits(db, (LOGIN_IP, ip_key), (LOGIN_EMAIL_IP, pair_key))

    user = db.scalar(select(User).where(User.email == email)) if email else None
    if user is None or user.password_hash is None:
        verify_dummy(data.password)  # то же время ответа, что при неверном пароле
        raise login_failed(db, ip_key, pair_key)
    if not verify_password(data.password, user.password_hash):
        raise login_failed(db, ip_key, pair_key)

    # Параметры хэширования могли измениться: обновляем хэш после успешного входа
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
        db.commit()

    clear(db, LOGIN_EMAIL_IP, pair_key)  # счётчик пары обнуляется, счётчик IP нет
    start_session(request, response, db, user)
    return user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def logout(request: Request, db: DbSession):
    """Выход всегда успешен: удаляет сессию из cookie (если есть) и саму cookie."""
    token = request.cookies.get(cookie_name())
    if token:
        delete_session(db, token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response