import re
from datetime import datetime, time
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

from app.emails import normalize_email
from app.timezones import is_valid_timezone
from app.urls import clean_url

MAX_BIGINT = 9_223_372_036_854_775_807
MAX_INIT_DATA_LENGTH = 8192

# Время напоминания: ровно ЧЧ:ММ, без секунд и без часового пояса
TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int | None
    email: str | None
    username: str | None
    timezone: str
    reminders_enabled: bool
    reminder_time: time
    email_verified_at: datetime | None

    @field_serializer("reminder_time")
    def serialize_reminder_time(self, value: time) -> str:
        return value.strftime("%H:%M")


class SettingsUpdate(BaseModel):
    """Изменяемые настройки пользователя. Любые другие поля запрещены."""

    model_config = ConfigDict(extra="forbid")

    timezone: str | None = None
    reminders_enabled: StrictBool | None = None
    reminder_time: time | None = None

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value):
        if value is not None and not is_valid_timezone(value):
            raise ValueError("Unknown time zone")
        return value

    @field_validator("reminder_time", mode="before")
    @classmethod
    def parse_reminder_time(cls, value):
        # До проверки pydantic: он принял бы секунды, смещение и числа
        if value is None:
            return None
        if not isinstance(value, str) or not TIME_RE.fullmatch(value):
            raise ValueError("reminder_time must look like HH:MM")
        return time(int(value[:2]), int(value[3:]))

    @model_validator(mode="after")
    def check_fields(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class CategoryCreate(BaseModel):
    name: CategoryName


class CategoryUpdate(BaseModel):
    name: CategoryName


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    contents_count: int


class ContentCreate(BaseModel):
    url: str | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None
    category_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        if value is None or not value.strip():
            return None
        return clean_url(value)

    @field_validator("note", "title")
    @classmethod
    def empty_to_none(cls, value):
        return value or None

    @model_validator(mode="after")
    def need_url_or_note(self):
        if self.url is None and self.note is None:
            raise ValueError("Provide url or note")
        return self


class ContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    title: str
    url: str | None
    description: str | None
    note: str | None
    content_type: str
    source: str
    image_url: str | None
    status: str
    studied_at: datetime | None
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None
    open_count: int

class ContentPage(BaseModel):
    items: list[ContentOut]
    total: int
    limit: int
    offset: int


ContentStatus = Literal["unseen", "planned", "studied", "irrelevant"]
ContentSource = Literal["youtube", "telegram", "web", "other"]
SortOrder = Literal["newest", "oldest", "title"]

class ContentUpdate(BaseModel):
    """Изменяемые поля материала. Любые другие поля запрещены."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)] | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None = None
    status: ContentStatus | None = None
    category_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)

    @model_validator(mode="after")
    def check_fields(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field")
        for name in ("title", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    init_data: Annotated[
        str, StringConstraints(min_length=1, max_length=MAX_INIT_DATA_LENGTH)
    ]


class AuthResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserOut

class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    # Пароль не обрезается и не меняется: пробелы по краям тоже часть пароля
    password: Annotated[str, StringConstraints(min_length=10, max_length=128)]
    consent: bool
    # Пояс браузера. Неизвестное значение не мешает регистрации: останется UTC
    timezone: str | None = None

    @field_validator("email")
    @classmethod
    def clean_email(cls, value):
        return normalize_email(value)

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value):
        if value is not True:
            raise ValueError("Consent is required")
        return value

    @field_validator("timezone")
    @classmethod
    def known_timezone_or_none(cls, value):
        return value if is_valid_timezone(value) else None

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Формат адреса здесь не проверяем строго: любой неподходящий вход даёт 401
    email: Annotated[str, StringConstraints(min_length=1, max_length=320)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, value):
        return normalize_email(value)


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Формат токена проверяет обработчик: любая ошибка даёт одинаковый 400
    token: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    password: Annotated[str, StringConstraints(min_length=10, max_length=128)]

class EmailVerificationConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Формат токена проверяет обработчик: любая ошибка даёт одинаковый 400
    token: Annotated[str, StringConstraints(min_length=1, max_length=256)]