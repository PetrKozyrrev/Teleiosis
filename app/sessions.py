"""Серверные сессии Mini App: выдача токена и хранение его хэша."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuthSession, User

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")

SESSION_LIFETIME = timedelta(hours=24)
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
    expires_at = now + SESSION_LIFETIME
    db.add(
        AuthSession(
            user_id=user.id, token_hash=hash_token(token), expires_at=expires_at
        )
    )
    db.commit()
    return token, expires_at



def find_user_by_token(db: Session, token: str) -> User | None:
    """Пользователь по токену сессии или None. Просроченная сессия не подходит."""
    if not TOKEN_RE.fullmatch(token):
        return None
    return db.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
    )