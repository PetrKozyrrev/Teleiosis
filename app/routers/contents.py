from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.activity import record_activity
from app.deps import CurrentUser, DbSession
from app.metadata import fetch_metadata
from app.models import Content
from app.routers.categories import get_own_category
from app.schemas import (
    MAX_BIGINT,
    ContentCreate,
    ContentOut,
    ContentPage,
    ContentSource,
    ContentStatus,
    ContentUpdate,
    SortOrder,
)
from app.urls import detect_source, normalize_url

router = APIRouter(prefix="/contents", tags=["contents"])

ContentId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]

# К каждой сортировке добавляется id, чтобы порядок был стабильным
SORT_ORDER = {
    "newest": (Content.created_at.desc(), Content.id.desc()),
    "oldest": (Content.created_at.asc(), Content.id.asc()),
    "title": (func.lower(Content.title), Content.id),
}


def make_title(url_normalized: str | None, note: str | None) -> str:
    if url_normalized:
        return url_normalized.removeprefix("https://")[:200]
    first_line = next((ln.strip() for ln in note.splitlines() if ln.strip()), "")
    return first_line[:80] or "Заметка"


def get_own_content(db: DbSession, user: CurrentUser, content_id: int) -> Content:
    """Материал ищется сразу с фильтром по владельцу.
    Чужой и несуществующий выглядят одинаково: 404."""
    content = db.scalar(
        select(Content).where(Content.id == content_id, Content.user_id == user.id)
    )
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    return content


def already_saved(existing_id: int) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail={"message": "Already saved", "existing_id": existing_id},
    )


@router.post("", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
def create_content(data: ContentCreate, db: DbSession, user: CurrentUser):
    # 1. Дешёвые проверки до любых обращений в интернет
    if data.category_id is not None:
        get_own_category(db, user, data.category_id)

    meta = None
    if data.url:
        url_normalized = normalize_url(data.url)
        source, content_type = detect_source(data.url)

        existing_id = db.scalar(
            select(Content.id).where(
                Content.user_id == user.id,
                Content.url_normalized == url_normalized,
            )
        )
        if existing_id is not None:
            raise already_saved(existing_id)

        # 2. Загрузка метаданных (никогда не падает: при неудаче вернёт None)
        meta = fetch_metadata(data.url)
    else:
        url_normalized, source, content_type = None, "other", "note"

    title = (
        data.title
        or (meta.title if meta else None)
        or make_title(url_normalized, data.note)
    )
    content = Content(
        user_id=user.id,
        category_id=data.category_id,
        title=title,
        url=data.url,
        url_normalized=url_normalized,
        description=meta.description if meta else None,
        image_url=meta.image_url if meta else None,
        note=data.note,
        content_type=content_type,
        source=source,
    )
    db.add(content)
    try:
        db.commit()
    except IntegrityError:
        # Редкая гонка: два одинаковых запроса одновременно
        db.rollback()
        existing_id = None
        if url_normalized:
            existing_id = db.scalar(
                select(Content.id).where(
                    Content.user_id == user.id,
                    Content.url_normalized == url_normalized,
                )
            )
        if existing_id is None:
            raise
        raise already_saved(existing_id)
    record_activity(db, user)
    db.refresh(content)
    return content


@router.get("", response_model=ContentPage)
def list_contents(
    db: DbSession,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[ContentStatus | None, Query(alias="status")] = None,
    source: ContentSource | None = None,
    category_id: Annotated[int | None, Query(gt=0, le=MAX_BIGINT)] = None,
    uncategorized: bool = False,
    sort: SortOrder = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
):
    if category_id is not None and uncategorized:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Use either category_id or uncategorized, not both",
        )

    # Главное условие изоляции: только материалы текущего пользователя
    conditions = [Content.user_id == user.id]
    if q and q.strip():
        conditions.append(Content.title.icontains(q.strip(), autoescape=True))
    if status_filter:
        conditions.append(Content.status == status_filter)
    if source:
        conditions.append(Content.source == source)
    if category_id is not None:
        conditions.append(Content.category_id == category_id)
    if uncategorized:
        conditions.append(Content.category_id.is_(None))

    total = db.scalar(select(func.count()).select_from(Content).where(*conditions))
    items = db.scalars(
        select(Content)
        .where(*conditions)
        .order_by(*SORT_ORDER[sort])
        .limit(limit)
        .offset(offset)
    ).all()
    return ContentPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{content_id}", response_model=ContentOut)
def read_content(content_id: ContentId, db: DbSession, user: CurrentUser):
    return get_own_content(db, user, content_id)


@router.patch("/{content_id}", response_model=ContentOut)
def update_content(
    content_id: ContentId, data: ContentUpdate, db: DbSession, user: CurrentUser
):
    content = get_own_content(db, user, content_id)
    changes = data.model_fields_set

    # 1. Сначала все проверки: при отказе ничего не должно измениться
    if "category_id" in changes and data.category_id is not None:
        get_own_category(db, user, data.category_id)

    note = data.note or None
    if "note" in changes and note is None and content.url is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A material without a link must keep its note",
        )

    # 2. Потом изменения
    if "category_id" in changes:
        content.category_id = data.category_id
    if "title" in changes:
        content.title = data.title
    if "note" in changes:
        content.note = note
    if "status" in changes and data.status != content.status:
        content.status = data.status
        content.studied_at = (
            datetime.now(timezone.utc) if data.status == "studied" else None
        )

    db.commit()
    record_activity(db, user)
    db.refresh(content)
    return content


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content(content_id: ContentId, db: DbSession, user: CurrentUser):
    content = get_own_content(db, user, content_id)
    db.delete(content)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{content_id}/open", status_code=status.HTTP_204_NO_CONTENT)
def record_open(content_id: ContentId, db: DbSession, user: CurrentUser):
    """Фиксирует открытие исходной ссылки (для метрики «доля материалов, к которым
    вернулись»). Счётчик растёт одной командой БД; updated_at не меняется, поэтому
    его значение задано явно (иначе сработал бы onupdate)."""
    result = db.execute(
        update(Content)
        .where(Content.id == content_id, Content.user_id == user.id)
        .values(
            open_count=Content.open_count + 1,
            last_opened_at=func.now(),
            updated_at=Content.updated_at,
        )
    )
    if result.rowcount == 0:
        # Чужой и несуществующий материал выглядят одинаково
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    db.commit()
    record_activity(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)