from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

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