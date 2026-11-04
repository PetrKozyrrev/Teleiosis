from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.urls import clean_url

MAX_BIGINT = 9_223_372_036_854_775_807

CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    timezone: str


class CategoryCreate(BaseModel):
    name: CategoryName


class CategoryUpdate(BaseModel):
    name: CategoryName


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


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

class ContentPage(BaseModel):
    items: list[ContentOut]
    total: int
    limit: int
    offset: int


ContentStatus = Literal["unseen", "planned", "studied", "irrelevant"]
ContentSource = Literal["youtube", "telegram", "web", "other"]
SortOrder = Literal["newest", "oldest", "title"]