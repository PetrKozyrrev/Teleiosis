"""Проверка подписи Telegram initData (Mini App).

Алгоритм по документации Telegram (core.telegram.org/bots/webapps):
  secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  hash       = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))
data_check_string: все поля кроме hash, отсортированные по имени,
в виде key=value через перевод строки.
"""

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.schemas import MAX_BIGINT

MAX_INIT_DATA_LENGTH = 8192
MAX_FIELDS = 50
DEFAULT_MAX_AGE_SECONDS = 3600  # как долго initData считается свежим
MAX_FUTURE_SKEW_SECONDS = 60  # допуск на расхождение часов
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{1,32}")
HASH_RE = re.compile(r"[0-9a-f]{64}")


class InitDataError(Exception):
    """Данные не прошли проверку.

    Текст это короткая причина для логов. В нём нет ни данных
    пользователя, ни секретов. Клиенту причину не показываем.
    """


@dataclass(frozen=True)
class VerifiedInitData:
    telegram_id: int
    username: str | None
    auth_date: int


def _parse(init_data: str) -> dict[str, str]:
    if not isinstance(init_data, str) or not init_data:
        raise InitDataError("empty or too long")
    if len(init_data) > MAX_INIT_DATA_LENGTH:
        raise InitDataError("empty or too long")
    try:
        pairs = parse_qsl(
            init_data, keep_blank_values=True, max_num_fields=MAX_FIELDS
        )
    except ValueError:
        raise InitDataError("malformed")
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            # Повторяющееся поле даёт неоднозначность: отказываем сразу
            raise InitDataError("duplicate field")
        fields[key] = value
    return fields


def compute_hash(fields: dict[str, str], bot_token: str) -> str:
    check_string = "\n".join(
        f"{key}={fields[key]}" for key in sorted(fields) if key != "hash"
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    return hmac.new(
        secret_key, check_string.encode(), hashlib.sha256
    ).hexdigest()


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age: int = DEFAULT_MAX_AGE_SECONDS,
    now: int | None = None,
) -> VerifiedInitData:
    """Проверяет подпись и свежесть initData. При любой проблеме бросает
    InitDataError. now нужен только тестам."""
    if not bot_token:
        raise InitDataError("bot token not configured")

    fields = _parse(init_data)

    # 1. Подпись (до любого использования содержимого)
    received = fields.get("hash")
    if received is None or not HASH_RE.fullmatch(received):
        raise InitDataError("bad hash format")
    expected = compute_hash(fields, bot_token)
    if not hmac.compare_digest(received, expected):
        raise InitDataError("bad signature")

    # 2. Свежесть
    raw_date = fields.get("auth_date", "")
    if not (raw_date.isascii() and raw_date.isdigit() and len(raw_date) <= 12):
        raise InitDataError("bad auth_date")
    auth_date = int(raw_date)
    current = int(time.time()) if now is None else now
    if current - auth_date > max_age:
        raise InitDataError("expired")
    if auth_date - current > MAX_FUTURE_SKEW_SECONDS:
        raise InitDataError("from the future")

    # 3. Пользователь
    raw_user = fields.get("user")
    if raw_user is None:
        raise InitDataError("no user")
    try:
        user = json.loads(raw_user)
    except ValueError:
        raise InitDataError("bad user")
    if not isinstance(user, dict):
        raise InitDataError("bad user")
    telegram_id = user.get("id")
    # type(...) is int отсекает True/False и дробные числа
    if type(telegram_id) is not int or not 0 < telegram_id <= MAX_BIGINT:
        raise InitDataError("bad user id")
    username = user.get("username")
    if not (isinstance(username, str) and USERNAME_RE.fullmatch(username)):
        username = None

    return VerifiedInitData(telegram_id, username, auth_date)