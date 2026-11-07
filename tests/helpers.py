"""Помощники для тестов: генерация подписанного initData.

Подпись считается здесь независимо от app/telegram_auth.py,
чтобы тест не проверял код его же копией.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

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