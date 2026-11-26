from datetime import datetime, timezone
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.activity import record_activity
from app.deps import CurrentUser, DbSession
from app.metadata import fetch_metadata
from app.models import Content, ContentSubmission, ContentGroup, LibraryGroup, User
from app.ratelimit import LINK_PREVIEW_USER, check_limits, make_key, record
from app.routers.categories import get_own_category
from app.schemas import (
    MAX_BIGINT,
    ContentCreate,
    ContentOut,
    ContentPage,
    ContentSource,
    ContentStatus,
    ContentUpdate,
    LinkPreviewInput,
    MobileContentCreate,
    MobileContentUpdate,
    SortOrder,
)
from app.urls import detect_source, normalize_url

router = APIRouter(prefix="/contents", tags=["contents"])
search_router = APIRouter(tags=["contents"])

ContentId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]

# К каждой сортировке добавляется id, чтобы порядок был стабильным
SORT_ORDER = {
    "newest": (Content.created_at.desc(), Content.id.desc()),
    "oldest": (Content.created_at.asc(), Content.id.asc()),
    "title": (func.lower(Content.title), Content.id),
}
SEARCH_COLUMNS = {
    "title": Content.title, "note": Content.note,
    "description": Content.description, "url": Content.url,
}
SearchScope = Literal["all", "title", "note", "description", "url"]


class ListFilters(BaseModel):
    q: str | None = Field(default=None, max_length=100)
    status: ContentStatus | None = None
    source: ContentSource | None = None
    content_type: Literal["video", "article"] | None = None
    category_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    uncategorized: bool = False
    tag_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    collection_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    sort: SortOrder = "newest"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)


class SearchFilters(ListFilters):
    search_in: SearchScope = "all"


def make_title(url_normalized: str | None, note: str | None) -> str:
    if url_normalized:
        return url_normalized.removeprefix("https://")[:200]
    first_line = next((ln.strip() for ln in note.splitlines() if ln.strip()), "")
    return first_line[:80] or "Заметка"


def get_own_content(db: DbSession, user: CurrentUser, content_id: int, *, lock: bool = False) -> Content:
    """Материал ищется сразу с фильтром по владельцу.
    Чужой и несуществующий выглядят одинаково: 404."""
    query = select(Content).where(Content.id == content_id, Content.user_id == user.id)
    content = db.scalar(query.with_for_update() if lock else query)
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
    return save_content(data, db, user)


@router.post("/submissions", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
@search_router.post("/submissions", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
def submit_content(data: MobileContentCreate, db: DbSession, user: CurrentUser,
                   key: Annotated[UUID, Header(alias="Idempotency-Key")]):
    # Existing receipts hash the original payload without an empty collection selection.
    fingerprint = sha256(data.model_dump_json(exclude=set() if data.collection_ids else {"collection_ids"}).encode()).hexdigest()
    lock = int.from_bytes(sha256(f"{user.id}/{key}".encode()).digest()[:8], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(lock)))
    receipt = db.get(ContentSubmission, (user.id, key))
    if receipt is not None:
        if receipt.fingerprint != fingerprint:
            raise HTTPException(409, {"code": "submission_payload_changed"})
        content = db.get(Content, receipt.content_id)
        if content is None:
            raise HTTPException(410, {"code": "submission_material_deleted"})
        if receipt.duplicate:
            raise already_saved(content.id)
        return content

    return save_content(data, db, user, key=key, fingerprint=fingerprint, collection_ids=data.collection_ids)


def verify_collections(db: DbSession, user: CurrentUser, ids: list[int]) -> None:
    if not ids:
        return
    owned = db.scalars(select(LibraryGroup.id).where(
        LibraryGroup.user_id == user.id, LibraryGroup.kind == "collection", LibraryGroup.id.in_(ids)
    ).order_by(LibraryGroup.id).with_for_update(read=True)).all()
    if len(owned) != len(ids):
        raise HTTPException(404, {"code": "collection_missing"})


def find_url_id(db: DbSession, user: CurrentUser, url_normalized: str) -> int | None:
    return db.scalar(select(Content.id).where(
        Content.user_id == user.id, Content.url_normalized == url_normalized
    ))


def save_content(data: ContentCreate, db: DbSession, user: CurrentUser, *,
                 key: UUID | None = None, fingerprint: str = "", collection_ids: list[int] | None = None):
    def save_receipt(content_id: int, *, duplicate: bool = False) -> None:
        if key is not None:
            db.add(ContentSubmission(user_id=user.id, key=key, fingerprint=fingerprint,
                                     content_id=content_id, duplicate=duplicate))

    def conflict(existing_id: int):
        if key is not None:
            save_receipt(existing_id, duplicate=True)
            db.commit()
        raise already_saved(existing_id)

    # 1. Дешёвые проверки до любых обращений в интернет
    if data.category_id is not None:
        get_own_category(db, user, data.category_id)
    if collection_ids:
        db.execute(select(User.id).where(User.id == user.id).with_for_update()).one()
        verify_collections(db, user, collection_ids)

    meta = None
    if data.url:
        url_normalized = normalize_url(data.url)
        source, content_type = detect_source(data.url)

        existing_id = find_url_id(db, user, url_normalized)
        if existing_id is not None:
            conflict(existing_id)

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
        content_type="video" if meta and meta.video_duration_seconds else content_type,
        video_duration_seconds=meta.video_duration_seconds if meta else None,
        text_character_count=meta.text_character_count if meta else None,
        source=source,
    )
    try:
        with db.begin_nested():
            db.add(content)
            db.flush()
    except IntegrityError:
        # Редкая гонка: два одинаковых запроса одновременно
        existing_id = find_url_id(db, user, url_normalized) if url_normalized else None
        if existing_id is not None:
            conflict(existing_id)
        raise
    save_receipt(content.id)
    for group_id in collection_ids or []:
        db.add(ContentGroup(user_id=user.id, content_id=content.id, group_id=group_id))
    db.commit()
    record_activity(db, user)
    db.refresh(content)
    return content


@router.get("", response_model=ContentPage)
def list_contents(db: DbSession, user: CurrentUser, filters: Annotated[ListFilters, Query()]):
    return content_page(db, user, filters, "title")


@search_router.get("/search", response_model=ContentPage)
def search_contents(db: DbSession, user: CurrentUser, filters: Annotated[SearchFilters, Query()]):
    return content_page(db, user, filters, filters.search_in)


@search_router.post("/link-preview")
def link_preview(data: LinkPreviewInput, response: Response, db: DbSession, user: CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    key = make_key(str(user.id))
    check_limits(db, (LINK_PREVIEW_USER, key))
    record(db, LINK_PREVIEW_USER, key)
    meta = fetch_metadata(data.url)
    _, kind = detect_source(data.url)
    return {"title": meta.title if meta else None, "image_url": meta.image_url if meta else None, "content_type": kind}


def content_page(db: DbSession, user: CurrentUser, filters: ListFilters, search_in: SearchScope):
    if filters.category_id is not None and filters.uncategorized:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Use either category_id or uncategorized, not both",
        )

    # Главное условие изоляции: только материалы текущего пользователя
    conditions = [Content.user_id == user.id]
    q = (filters.q or "").strip()
    if q:
        if "\x00" in q:
            raise HTTPException(422, "Invalid search text")
        columns = SEARCH_COLUMNS.values() if search_in == "all" else (SEARCH_COLUMNS[search_in],)
        conditions.append(or_(*(column.icontains(q, autoescape=True) for column in columns)))
    if filters.status:
        conditions.append(Content.status == filters.status)
    if filters.source:
        conditions.append(Content.source == filters.source)
    if filters.content_type:
        conditions.append(Content.content_type == filters.content_type)
    if filters.category_id is not None:
        conditions.append(Content.category_id == filters.category_id)
    if filters.uncategorized:
        conditions.append(Content.category_id.is_(None))

    for group_id, kind in ((filters.tag_id, "tag"), (filters.collection_id, "collection")):
        if group_id is not None:
            conditions.append(select(ContentGroup.content_id).join(
                LibraryGroup, LibraryGroup.id == ContentGroup.group_id).where(
                    ContentGroup.user_id == user.id, ContentGroup.content_id == Content.id,
                    LibraryGroup.user_id == user.id, LibraryGroup.id == group_id,
                    LibraryGroup.kind == kind).exists())

    total = db.scalar(select(func.count()).select_from(Content).where(*conditions))
    items = db.scalars(
        select(Content)
        .where(*conditions)
        .order_by(*SORT_ORDER[filters.sort])
        .limit(filters.limit)
        .offset(filters.offset)
    ).all()
    return ContentPage(items=items, total=total, limit=filters.limit, offset=filters.offset)


@router.get("/{content_id}", response_model=ContentOut)
def read_content(content_id: ContentId, db: DbSession, user: CurrentUser):
    return get_own_content(db, user, content_id)


@router.patch("/{content_id}", response_model=ContentOut)
def update_content(
    content_id: ContentId, data: ContentUpdate, db: DbSession, user: CurrentUser
):
    return change_content(content_id, data, db, user)


@router.patch("/{content_id}/versioned", response_model=ContentOut)
def update_versioned_content(
    content_id: ContentId, data: MobileContentUpdate, db: DbSession, user: CurrentUser,
    if_match: Annotated[str, Header(pattern=r'^"[1-9][0-9]{0,18}"$')],
):
    return change_content(content_id, data, db, user, version=int(if_match[1:-1]))


def change_content(content_id: int, data: ContentUpdate | MobileContentUpdate, db: DbSession,
                   user: CurrentUser, *, version: int | None = None):
    collections = data.collection_ids if isinstance(data, MobileContentUpdate) else None
    if collections is not None:
        # Same lock order as the organization endpoints.
        db.execute(select(User.id).where(User.id == user.id).with_for_update()).one()
        verify_collections(db, user, collections)
    content = get_own_content(db, user, content_id, lock=True)
    if version is not None and content.version != version:
        raise HTTPException(412, {"code": "content_version_changed"})
    changes = data.model_fields_set
    new_url = data.url if isinstance(data, MobileContentUpdate) else None
    if new_url is not None and (content.url is None or content.content_type == "pdf"):
        raise HTTPException(422, {"code": "material_has_no_editable_link"})
    normalized = normalize_url(new_url) if new_url is not None else None
    if normalized is not None and normalized != content.url_normalized:
        existing_id = find_url_id(db, user, normalized)
        if existing_id is not None:
            raise already_saved(existing_id)

    # 1. Сначала все проверки: при отказе ничего не должно измениться
    if "category_id" in changes and data.category_id is not None:
        get_own_category(db, user, data.category_id)

    note = data.note or None
    if "note" in changes and note is None and content.url is None and content.content_type != "pdf":
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
    if data.status is not None:
        apply_content_status(content, data.status, datetime.now(timezone.utc))

    if new_url is not None and new_url != content.url:
        meta = fetch_metadata(new_url)
        content.url = new_url
        content.url_normalized = normalized
        content.source, content.content_type = detect_source(new_url)
        if meta and meta.video_duration_seconds:
            content.content_type = "video"
        content.video_duration_seconds = meta.video_duration_seconds if meta else None
        content.text_character_count = meta.text_character_count if meta else None
        content.description = meta.description if meta else None
        content.image_url = meta.image_url if meta else None
    if collections is not None:
        existing = set(db.scalars(select(ContentGroup.group_id).join(LibraryGroup).where(
            ContentGroup.user_id == user.id, ContentGroup.content_id == content.id,
            LibraryGroup.kind == "collection"
        )))
        selected = set(collections)
        if existing != selected:
            db.execute(delete(ContentGroup).where(ContentGroup.user_id == user.id,
                ContentGroup.content_id == content.id, ContentGroup.group_id.in_(existing - selected)))
            db.add_all(ContentGroup(user_id=user.id, content_id=content.id, group_id=group_id)
                       for group_id in selected - existing)
            content.version += 1
            content.updated_at = func.now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_id = find_url_id(db, user, normalized) if normalized is not None else None
        if existing_id is not None and existing_id != content_id:
            raise already_saved(existing_id)
        raise
    record_activity(db, user)
    db.refresh(content)
    return content


def apply_content_status(content: Content, status: ContentStatus, now: datetime) -> None:
    if content.status != status:
        content.status = status
        content.studied_at = now if status == "studied" else None


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
