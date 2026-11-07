"""Помощники для тестов: генерация подписанного initData и вход по токену.

Подпись считается здесь независимо от app/telegram_auth.py,
чтобы тест не проверял код его же копией.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.deps import get_or_create_user
from app.sessions import create_session

# Тестовая сессия БД и выданные в ней токены. Выставляется в conftest.py.
_state: dict = {"session": None, "headers": {}}

USER = {"id": 42, "first_name": "Иван", "username": "ivan_1"}


def sign(fields: dict[str, str], bot_token: str) -> str:
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()


def build_init_data(
    bot_token: str,
    *,
    user: dict | None = USER,
    auth_date: int | None = None,
    extra: dict[str, str] | None = None,
    drop: tuple[str, ...] = (),
) -> str:
    """Строка initData с корректной подписью.

    user=None: без поля user. extra: добавить или заменить поля до подписи.
    drop: убрать поля до подписи.
    """
    date = int(time.time()) if auth_date is None else auth_date
    fields = {"auth_date": str(date), "query_id": "AAH-test"}
    if user is not None:
        fields["user"] = json.dumps(user, separators=(",", ":"), ensure_ascii=False)
    fields.update(extra or {})
    for name in drop:
        fields.pop(name, None)
    fields["hash"] = sign(fields, bot_token)
    return urlencode(fields)



def bind_session(session) -> None:
    """Вызывается из conftest.py: запоминает сессию БД текущего теста."""
    _state["session"] = session
    _state["headers"] = {}


def auth_headers(telegram_id: int) -> dict[str, str]:
    """Заголовок входа по токену для пользователя с этим Telegram ID.

    Создаёт пользователя и настоящую сессию в тестовой БД (теми же функциями,
    что и боевой код). Повторный вызов в том же тесте возвращает тот же токен.
    """
    session = _state["session"]
    if session is None:
        raise RuntimeError("auth_headers нужен тест с фикстурой session или client")
    cache = _state["headers"]
    if telegram_id not in cache:
        user = get_or_create_user(session, telegram_id)
        token, _ = create_session(session, user)
        cache[telegram_id] = {"Authorization": f"Bearer {token}"}
    return dict(cache[telegram_id])