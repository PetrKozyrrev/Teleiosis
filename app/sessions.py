"""Серверные сессии: выдача токена, поиск, продление, удаление."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuthSession, User

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")

SESSION_IDLE = timedelta(days=14)  # сколько живёт сессия без использования
SESSION_ABSOLUTE = timedelta(days=60)  # максимум от создания, продлением не обойти
RENEW_STEP = timedelta(days=1)  # продлеваем, только если выигрыш не меньше суток
MAX_SESSIONS_PER_USER = 10


def hash_token(token: str) -> str:
    """SHA-256 от токена в hex (64 символа). Сам токен в БД не хранится."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, datetime]:
    """Создаёт сессию. Возвращает (токен, срок действия).
    Токен виден только здесь и в ответе клиенту, в БД его нет."""
    now = datetime.now(timezone.utc)

    # 1. Удаляем просроченные сессии этого пользователя
    db.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id, AuthSession.expires_at <= now
        )
    )

    # 2. Оставляем место для новой: максимум MAX_SESSIONS_PER_USER активных
    surplus_ids = db.scalars(
        select(AuthSession.id)
        .where(AuthSession.user_id == user.id)
        .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())
        .offset(MAX_SESSIONS_PER_USER - 1)
    ).all()
    if surplus_ids:
        db.execute(delete(AuthSession).where(AuthSession.id.in_(surplus_ids)))

    # 3. Новая сессия
    token = secrets.token_urlsafe(32)
    expires_at = now + SESSION_IDLE
    db.add(
        AuthSession(
            user_id=user.id, token_hash=hash_token(token), expires_at=expires_at
        )
    )
    db.commit()
    return token, expires_at


def renew_session(db: Session, row: AuthSession, now: datetime) -> bool:
    """Продлевает сессию до now + SESSION_IDLE, но не дальше created_at + SESSION_ABSOLUTE.
    Не чаще, чем даёт выигрыш в RENEW_STEP: чтобы не писать в БД на каждый запрос."""
    target = min(now + SESSION_IDLE, row.created_at + SESSION_ABSOLUTE)
    if target - row.expires_at < RENEW_STEP:
        return False
    row.expires_at = target
    db.commit()
    return True


def find_user_by_token(db: Session, token: str) -> User | None:
    """Пользователь по токену сессии или None. Просроченная сессия не подходит.
    Успешное обращение продлевает сессию."""
    if not TOKEN_RE.fullmatch(token):
        return None
    now = datetime.now(timezone.utc)
    row = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > now,
        )
    )
    if row is None:
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    renew_session(db, row, now)
    return user


def delete_session(db: Session, token: str) -> None:
    """Удаляет сессию по токену (если есть). Незнакомый токен не ошибка."""
    if not TOKEN_RE.fullmatch(token):
        return
    db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    db.commit()