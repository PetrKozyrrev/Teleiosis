from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Identity,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR telegram_id IS NOT NULL",
            name="ck_users_login_method",
        ),
        CheckConstraint("email = lower(email)", name="ck_users_email_lower"),
        CheckConstraint("char_length(email) <= 254", name="ck_users_email_len"),
        CheckConstraint(
            "password_hash IS NULL OR email IS NOT NULL",
            name="ck_users_password_needs_email",
        ),
        CheckConstraint(
            "(consent_at IS NULL) = (consent_version IS NULL)",
            name="ck_users_consent_pair",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Нужен только пользователям, пришедшим из Telegram (бот заморожен)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(Text)
    # Вход на сайте. Адрес всегда в нижнем регистре (проверяет CHECK в БД)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Согласие на обработку персональных данных: когда и какая версия текста
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, server_default="UTC")
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    reminder_time: Mapped[time] = mapped_column(Time, server_default=text("'09:00'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    categories: Mapped[list["Category"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    contents: Mapped[list["Content"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_categories_user_name"),
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 50", name="ck_categories_name_len"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="categories")


class Content(Base):
    __tablename__ = "contents"
    __table_args__ = (
        UniqueConstraint("user_id", "url_normalized", name="uq_contents_user_url"),
        CheckConstraint(
            "status IN ('unseen','planned','studied','irrelevant')",
            name="ck_contents_status",
        ),
        CheckConstraint(
            "url IS NOT NULL OR note IS NOT NULL", name="ck_contents_url_or_note"
        ),
        Index("ix_contents_user_created", "user_id", text("created_at DESC")),
        Index("ix_contents_user_status", "user_id", "status"),
        Index("ix_contents_user_category", "user_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    url_normalized: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text, server_default="other")
    source: Mapped[str] = mapped_column(Text, server_default="other")
    image_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="unseen")
    studied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="contents")
    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="content", cascade="all, delete-orphan", passive_deletes=True
    )


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','sent','cancelled')", name="ck_reminders_status"
        ),
        Index(
            "ix_reminders_pending",
            "scheduled_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_reminders_content", "content_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    content_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contents.id", ondelete="CASCADE")
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    content: Mapped["Content"] = relationship(back_populates="reminders")

class AuthSession(Base):
    """Серверная сессия Mini App. Хранится только хэш токена, не сам токен."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "char_length(token_hash) = 64", name="ck_auth_sessions_hash_len"
        ),
        CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry"),
        Index("ix_auth_sessions_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class RateLimitEvent(Base):
    """Журнал попыток для ограничения частоты запросов.

    Хранится не адрес и не e-mail, а SHA-256 от них. Записи старше нескольких
    часов удаляются кодом (app/ratelimit.py)."""

    __tablename__ = "rate_limit_events"
    __table_args__ = (
        CheckConstraint(
            "char_length(key_hash) = 64", name="ck_rate_limit_hash_len"
        ),
        Index("ix_rate_limit_lookup", "bucket", "key_hash", "created_at"),
        Index("ix_rate_limit_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    bucket: Mapped[str] = mapped_column(Text)
    key_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class PasswordResetToken(Base):
    """Одноразовый токен сброса пароля. Хранится только хэш токена;
    после использования строка удаляется."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        CheckConstraint(
            "char_length(token_hash) = 64", name="ck_password_reset_hash_len"
        ),
        CheckConstraint("expires_at > created_at", name="ck_password_reset_expiry"),
        Index("ix_password_reset_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))