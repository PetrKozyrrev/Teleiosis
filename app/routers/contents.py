from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import Content
from app.routers.categories import get_own_category
from app.schemas import ContentCreate, ContentOut
from app.urls import detect_source, normalize_url

router = APIRouter(prefix="/contents", tags=["contents"])


def make_title(url_normalized: str | None, note: str | None) -> str:
    if url_normalized:
        return url_normalized.removeprefix("https://")[:200]
    first_line = next((ln.strip() for ln in note.splitlines() if ln.strip()), "")
    return first_line[:80] or "Заметка"


@router.post("", response_model=ContentOut, status_code=status.HTTP_201_CREATED)
def create_content(data: ContentCreate, db: DbSession, user: CurrentUser):
    # Категория должна принадлежать этому же пользователю (иначе 404)
    if data.category_id is not None:
        get_own_category(db, user, data.category_id)

    if data.url:
        url_normalized = normalize_url(data.url)
        source, content_type = detect_source(data.url)
    else:
        url_normalized, source, content_type = None, "other", "note"

    content = Content(
        user_id=user.id,
        category_id=data.category_id,
        title=data.title or make_title(url_normalized, data.note),
        url=data.url,
        url_normalized=url_normalized,
        note=data.note,
        content_type=content_type,
        source=source,
    )
    db.add(content)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = None
        if url_normalized:
            existing = db.scalar(
                select(Content).where(
                    Content.user_id == user.id,
                    Content.url_normalized == url_normalized,
                )
            )
        if existing is None:
            raise
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "Already saved", "existing_id": existing.id},
        )
    db.refresh(content)
    return content


@router.get("/{content_id}", response_model=ContentOut)
def read_content(content_id: int, db: DbSession, user: CurrentUser):
    content = db.scalar(
        select(Content).where(Content.id == content_id, Content.user_id == user.id)
    )
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    return content