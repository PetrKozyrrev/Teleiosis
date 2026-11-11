"""Ссылки отписки от писем: подписанный токен, в БД ничего не хранится.

Токен: "<user_id>.<hex HMAC-SHA256>". Подписывается строка "unsubscribe:<user_id>"
ключом SECRET_KEY. Срока жизни нет: ссылка из старого письма должна работать.
Токен позволяет только отключить напоминания, ничего больше."""

import hashlib
import hmac
import re

from app.config import MIN_SECRET_KEY_LENGTH, settings
from app.schemas import MAX_BIGINT

TOKEN_RE = re.compile(r"[1-9][0-9]{0,18}\.[0-9a-f]{64}")


class SecretKeyMissing(RuntimeError):
    """SECRET_KEY не задан или короче допустимого."""


def _mac(user_id: int) -> str:
    key = settings.secret_key
    if len(key) < MIN_SECRET_KEY_LENGTH:
        raise SecretKeyMissing("SECRET_KEY is not configured")
    return hmac.new(
        key.encode(), f"unsubscribe:{user_id}".encode(), hashlib.sha256
    ).hexdigest()


def make_token(user_id: int) -> str:
    return f"{user_id}.{_mac(user_id)}"


def verify_token(token: object) -> int | None:
    """user_id, если подпись верна, иначе None. Бросает SecretKeyMissing,
    если ключ не настроен (но только для токена правильного формата)."""
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        return None
    raw_id, _, received = token.partition(".")
    user_id = int(raw_id)
    if user_id > MAX_BIGINT:
        return None
    if not hmac.compare_digest(received, _mac(user_id)):
        return None
    return user_id


def page_link(user_id: int) -> str:
    """Ссылка для текста письма: токен во фрагменте, на сервер не уходит."""
    return f"{settings.app_origin}/app/unsubscribe.html#token={make_token(user_id)}"


def one_click_url(user_id: int) -> str:
    """Адрес для заголовка List-Unsubscribe: на него почтовый сервис шлёт POST."""
    return f"{settings.app_origin}/auth/unsubscribe/one-click?token={make_token(user_id)}"


def unsubscribe_headers(user_id: int) -> dict[str, str]:
    """Заголовки RFC 8058 для письма (DKIM-подпись, покрывающую их, ставит провайдер)."""
    return {
        "List-Unsubscribe": f"<{one_click_url(user_id)}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }