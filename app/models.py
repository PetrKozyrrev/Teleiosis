from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Identity,
    Text,
    Time,
    UniqueConstraint,
    DDL,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lower"),
        CheckConstraint("char_length(email) <= 254", name="ck_users_email_len"),
        CheckConstraint(
            "(consent_at IS NULL) = (consent_version IS NULL)",
            name="ck_users_consent_pair",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Вход на сайте. Адрес всегда в нижнем регистре (проверяет CHECK в БД)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Согласие на обработку персональных данных: когда и какая версия текста
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, server_default="UTC")
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    reminder_time: Mapped[time] = mapped_column(Time, server_default=text("'09:00'"))
    # Локальная дата (в поясе пользователя) последней отправленной подборки.
    # Защита от двойной отправки: см. decisions.md от 10.11.2026
    last_digest_on: Mapped[date | None] = mapped_column(Date)
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
        # Названия уникальны без учёта регистра: «Бизнес» и «бизнес» это одна категория.
        # Выражение задано через text(): так alembic check не даёт ложных расхождений.
        Index("uq_categories_user_lower_name", "user_id", text("lower(name)"), unique=True),
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
        UniqueConstraint("id", "user_id", name="uq_contents_id_user"),
        CheckConstraint(
            "status IN ('unseen','planned','studied','irrelevant')",
            name="ck_contents_status",
        ),
        CheckConstraint(
            "url IS NOT NULL OR note IS NOT NULL OR content_type = 'pdf'", name="ck_contents_url_or_note"
        ),
        CheckConstraint("open_count >= 0", name="ck_contents_open_count"),
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
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
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


# Runs on direct SQL and on the FK action that clears category_id.
event.listen(Content.__table__, "after_create", DDL("""
CREATE OR REPLACE FUNCTION increment_content_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.title, NEW.note, NEW.category_id, NEW.status)
        IS DISTINCT FROM ROW(OLD.title, OLD.note, OLD.category_id, OLD.status) THEN
        NEW.version := OLD.version + 1;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER contents_version BEFORE UPDATE ON contents
FOR EACH ROW EXECUTE FUNCTION increment_content_version();
""").execute_if(dialect="postgresql"))
event.listen(Content.__table__, "after_drop", DDL(
    "DROP FUNCTION IF EXISTS increment_content_version()"
).execute_if(dialect="postgresql"))


class LibraryGroup(Base):
    __tablename__ = "library_groups"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_library_groups_id_user"),
        Index("uq_library_groups_owner_kind_name", "user_id", "kind", text("lower(name)"), unique=True),
        CheckConstraint("kind IN ('tag', 'collection')", name="ck_library_groups_kind"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 50", name="ck_library_groups_name_len"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentGroup(Base):
    __tablename__ = "content_groups"
    __table_args__ = (
        ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"],
                             ondelete="CASCADE", name="fk_content_groups_content_owner"),
        ForeignKeyConstraint(["group_id", "user_id"], ["library_groups.id", "library_groups.user_id"],
                             ondelete="CASCADE", name="fk_content_groups_group_owner"),
        Index("ix_content_groups_owner_group", "user_id", "group_id", "content_id"),
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    group_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class LibraryImport(Base):
    __tablename__ = "library_imports"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    digest: Mapped[str] = mapped_column(Text, primary_key=True)
    summary: Mapped[dict] = mapped_column(JSON)


class PdfObject(Base):
    __tablename__ = "pdf_objects"
    __table_args__ = (
        ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"],
                             ondelete="SET NULL", name="fk_pdf_objects_content_owner"),
        UniqueConstraint("content_id", name="uq_pdf_objects_content"),
        UniqueConstraint("user_id", "digest", name="uq_pdf_objects_owner_digest"),
        CheckConstraint("size_bytes BETWEEN 1 AND 10485760", name="ck_pdf_objects_size"),
        CheckConstraint("(user_id IS NULL) = (content_id IS NULL)", name="ck_pdf_objects_ownership"),
        Index("ix_pdf_objects_charged_user", "charged_user_id"),
        Index("ix_pdf_objects_cleanup", "created_at", "id", postgresql_where=text("published IS FALSE OR user_id IS NULL")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    content_id: Mapped[int | None] = mapped_column(BigInteger)
    charged_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    digest: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    creating: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ContentSubmission(Base):
    __tablename__ = "content_submissions"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(Text)
    # Intentionally independent of the material's lifetime.
    content_id: Mapped[int] = mapped_column(BigInteger)
    duplicate: Mapped[bool] = mapped_column(Boolean)


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
        # У материала не больше одного ожидающего напоминания
        Index(
            "uq_reminders_content_pending",
            "content_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
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
    """Сессия сайта или mobile. Хранится только хэш токена, не сам токен."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "char_length(token_hash) = 64", name="ck_auth_sessions_hash_len"
        ),
        CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry"),
        CheckConstraint("client_type IN ('web', 'mobile')", name="ck_auth_sessions_client_type"),
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

    client_type: Mapped[str] = mapped_column(Text, server_default="web")

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


class EmailVerificationToken(Base):
    """Одноразовый токен подтверждения e-mail. Хранится только хэш токена;
    после использования строка удаляется."""

    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        CheckConstraint(
            "char_length(token_hash) = 64", name="ck_email_verification_hash_len"
        ),
        CheckConstraint(
            "expires_at > created_at", name="ck_email_verification_expiry"
        ),
        Index("ix_email_verification_user", "user_id"),
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




class UserActivity(Base):
    """Активный день пользователя: в этот (местный) день он сделал хотя бы одно
    действие с материалами. Одна строка на пользователя и день. Нужна для метрик
    возврата; удаляется вместе с аккаунтом."""

    __tablename__ = "user_activity"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class PushDevice(Base):
    __tablename__ = "push_devices"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_push_devices_token_hash"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("auth_sessions.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
    enabled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PushDelivery(Base):
    __tablename__ = "push_deliveries"
    __table_args__ = (
        UniqueConstraint("device_id", "event_key", name="uq_push_deliveries_event_device"),
        CheckConstraint("status IN ('pending','sending','retry_wait','accepted','cancelled','expired','failed')", name="ck_push_deliveries_status"),
        Index("ix_push_deliveries_due", "status", "next_attempt_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    device_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("push_devices.id", ondelete="CASCADE"))
    content_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contents.id", ondelete="CASCADE"))
    reminder_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("reminders.id", ondelete="CASCADE"))
    event_key: Mapped[str] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    reason: Mapped[str | None] = mapped_column(Text)


class StudyGoal(Base):
    __tablename__ = "study_goals"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_study_goal_owner"),
        Index("uq_study_goal_name", "user_id", text("lower(name)"), unique=True),
        CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_study_goal_name"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)


class WeekBudget(Base):
    __tablename__ = "week_budgets"
    __table_args__ = (
        CheckConstraint("minutes BETWEEN 1 AND 10080", name="ck_week_budget_minutes"),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    week: Mapped[date] = mapped_column(Date, primary_key=True)
    minutes: Mapped[int] = mapped_column(Integer)


class StudyTask(Base):
    __tablename__ = "study_tasks"
    __table_args__ = (
        ForeignKeyConstraint(["goal_id", "user_id"], ["study_goals.id", "study_goals.user_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["content_id", "user_id"], ["contents.id", "contents.user_id"], ondelete="CASCADE"),
        UniqueConstraint("goal_id", "content_id", name="uq_study_task_material"),
        CheckConstraint("minutes BETWEEN 1 AND 1440", name="ck_study_task_minutes"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="ck_study_task_priority"),
        Index("ix_study_task_owner_day", "user_id", "day"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    goal_id: Mapped[int] = mapped_column(BigInteger)
    content_id: Mapped[int] = mapped_column(BigInteger)
    day: Mapped[date] = mapped_column(Date)
    minutes: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class StudyTaskEvent(Base):
    __tablename__ = "study_task_events"
    task_id: Mapped[int] = mapped_column(ForeignKey("study_tasks.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    day: Mapped[date] = mapped_column(Date)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
