"""Cookie сессии сайта."""

from fastapi import Response

from app.config import settings
from app.sessions import SESSION_ABSOLUTE


def cookie_name() -> str:
    # Префикс __Host- обязывает браузер требовать Secure, Path=/ и отсутствие Domain.
    # На http://localhost Secure не работает, поэтому в разработке имя обычное.
    return "__Host-session" if settings.cookie_secure else "session"


def set_session_cookie(response: Response, token: str) -> None:
    # Cookie живёт до абсолютного максимума; действительность сессии решает сервер
    response.set_cookie(
        key=cookie_name(),
        value=token,
        max_age=int(SESSION_ABSOLUTE.total_seconds()),
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    # Атрибуты те же, что при установке: иначе браузер может не удалить cookie
    response.delete_cookie(
        key=cookie_name(),
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )