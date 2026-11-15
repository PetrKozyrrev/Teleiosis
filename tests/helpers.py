"""Помощники тестов: пользователи с e-mail и сессии сайта."""

from sqlalchemy import select

from app.models import User
from app.sessions import create_session

ORIGIN = "http://localhost:8000"
_state: dict = {"session": None, "headers": {}}


def bind_session(session) -> None:
    """Каждый тест получает отдельную сессию БД и кэш учётных данных."""
    _state["session"] = session
    _state["headers"] = {}


def auth_headers(user_key: int) -> dict[str, str]:
    """Cookie и Origin для тестового пользователя user{user_key}@example.com."""
    session = _state["session"]
    if session is None:
        raise RuntimeError("auth_headers нужен тест с фикстурой session или client")
    cache = _state["headers"]
    if user_key not in cache:
        email = f"user{user_key}@example.com"
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email)
            session.add(user)
            session.flush()
        token, _ = create_session(session, user)
        cache[user_key] = {"Cookie": f"session={token}", "Origin": ORIGIN}
    return dict(cache[user_key])
