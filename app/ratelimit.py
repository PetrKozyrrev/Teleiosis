"""Ограничение частоты запросов: журнал попыток в PostgreSQL.

В журнале лежит не адрес и не e-mail, а SHA-256 от них: так персональные данные
не хранятся открытым текстом. Это не защита от целенаправленного перебора
(пространство IPv4 мало): записи живут не дольше RETENTION и удаляются.

Проверка и запись не атомарны: при одновременных запросах лимит может быть
превышен на единицы попыток. Для защиты от перебора этого достаточно.
"""

import hashlib
import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import RateLimitEvent

# Записи старше этого срока удаляются (дольше самого длинного окна)
RETENTION = timedelta(hours=2)

@dataclass(frozen=True)
class Rule:
    bucket: str  # название счётчика
    limit: int  # сколько попыток разрешено
    window: timedelta  # за какой период


LOGIN_IP = Rule("login_ip", 30, timedelta(minutes=15))
LOGIN_EMAIL_IP = Rule("login_email_ip", 5, timedelta(minutes=15))
REGISTER_IP = Rule("register_ip", 5, timedelta(hours=1))

RESET_EMAIL = Rule("reset_email", 3, timedelta(hours=1))
RESET_IP = Rule("reset_ip", 10, timedelta(hours=1))


def client_ip(request: Request) -> str:
    """Адрес клиента для счётчиков. IPv6 сводится к сети /64.

    Адрес берётся из request.client: за доверенным прокси его подменяет uvicorn
    (настройка forwarded-allow-ips), сами заголовки мы не читаем."""
    host = request.client.host if request.client else "unknown"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)
    return str(ip)


def make_key(*parts: str) -> str:
    """SHA-256 от частей ключа (адрес, e-mail). Разделитель исключает склейки."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def blocked_for(db: Session, rule: Rule, key: str) -> int | None:
    """Через сколько секунд снова можно пробовать, или None, если лимит не исчерпан."""
    now = datetime.now(timezone.utc)
    count, oldest = db.execute(
        select(func.count(), func.min(RateLimitEvent.created_at)).where(
            RateLimitEvent.bucket == rule.bucket,
            RateLimitEvent.key_hash == key,
            RateLimitEvent.created_at > now - rule.window,
        )
    ).one()
    if count < rule.limit:
        return None
    wait = (oldest + rule.window - now).total_seconds()
    return max(1, ceil(wait))


def too_many_requests(seconds: int) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many attempts. Try again later.",
        headers={"Retry-After": str(seconds)},
    )


def check_limits(db: Session, *checks: tuple[Rule, str]) -> None:
    """Бросает 429, если исчерпан хотя бы один лимит (ждать нужно дольше всех)."""
    waits = [w for rule, key in checks if (w := blocked_for(db, rule, key)) is not None]
    if waits:
        raise too_many_requests(max(waits))


def record(db: Session, rule: Rule, key: str) -> None:
    """Записывает попытку и заодно удаляет устаревшие записи."""
    now = datetime.now(timezone.utc)
    db.add(RateLimitEvent(bucket=rule.bucket, key_hash=key, created_at=now))
    db.execute(delete(RateLimitEvent).where(RateLimitEvent.created_at < now - RETENTION))
    db.commit()


def clear(db: Session, rule: Rule, key: str) -> None:
    """Обнуляет счётчик (после успешного входа)."""
    db.execute(
        delete(RateLimitEvent).where(
            RateLimitEvent.bucket == rule.bucket, RateLimitEvent.key_hash == key
        )
    )
    db.commit()