"""Хэширование паролей (Argon2id). Пароли нигде не логируются."""

import logging
import threading

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

logger = logging.getLogger(__name__)

# Одновременно считаются не больше HASH_CONCURRENCY хэшей: каждый занимает
# около 64 МиБ памяти, а лишние запросы просто ждут своей очереди.
HASH_CONCURRENCY = 4
_slots = threading.BoundedSemaphore(HASH_CONCURRENCY)

# Параметры по умолчанию библиотеки (Argon2id, профиль RFC 9106 low memory)
_hasher = PasswordHasher()

# Хэш несуществующего пароля. Нужен, чтобы вход с несуществующим e-mail
# занимал столько же времени, сколько вход с существующим.
_DUMMY_HASH = _hasher.hash("teleiosis-dummy-password-for-timing")


def hash_password(password: str) -> str:
    """Строка Argon2id целиком (соль и параметры внутри)."""
    with _slots:
        return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True, только если пароль подходит. Любая ошибка проверки даёт False."""
    try:
        with _slots:
            return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception as exc:  # намеренно широко: битый хэш не должен давать вход
        logger.warning("password verification error: %s", type(exc).__name__)
        return False


def needs_rehash(password_hash: str) -> bool:
    """True, если хэш создан с другими параметрами, чем текущие."""
    return _hasher.check_needs_rehash(password_hash)


def verify_dummy(password: str) -> None:
    """Тратит столько же времени, сколько обычная проверка. Результат не нужен."""
    verify_password(password, _DUMMY_HASH)