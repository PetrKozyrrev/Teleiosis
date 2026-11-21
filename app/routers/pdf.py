from collections.abc import AsyncIterator
from hashlib import sha256
from threading import BoundedSemaphore
from typing import Annotated
from urllib.parse import quote, unquote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select

from app import pdf_storage as storage
from app.activity import record_activity
from app.config import settings
from app.deps import CurrentUser, DbSession
from app.models import Category, Content, PdfObject, User
from app.routers.contents import ContentId, get_own_content
from app.schemas import MAX_BIGINT, ContentOut

router = APIRouter(tags=["pdf"])
upload_slots = BoundedSemaphore(2)
download_slots = BoundedSemaphore(4)


class PdfMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    size_bytes: int
    published: bool


def require_pdf():
    if not settings.pdf_enabled:
        raise HTTPException(503, {"code": "pdf_disabled"})


def owned_pdf(db: DbSession, owner: int, content_id: int):
    return db.scalar(select(PdfObject).where(PdfObject.user_id == owner, PdfObject.content_id == content_id))


def target_id(content_id: ContentId, db: DbSession, user: CurrentUser):
    require_pdf()
    return get_own_content(db, user, content_id).id


TargetId = Annotated[int, Depends(target_id)]


async def read_upload(request: Request, _user: CurrentUser) -> AsyncIterator[tuple[str, str, bytes]]:
    require_pdf()
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/pdf":
        raise HTTPException(415, {"code": "pdf_required"})
    name = unquote(request.headers.get("X-Teleiosis-Filename", "document.pdf")).strip()
    if (not name.lower().endswith(".pdf") or len(name) > 120 or len(name) <= 4
        or "/" in name or "\\" in name or not name.isprintable() or "\ufffd" in name):
        raise HTTPException(422, {"code": "invalid_pdf_name"})
    title = unquote(request.headers.get("X-Teleiosis-Pdf-Title", "")).strip() or name[:-4].strip() or name
    if len(title) > 300 or not title.isprintable() or "\ufffd" in title:
        raise HTTPException(422, {"code": "invalid_pdf_title"})
    if not upload_slots.acquire(blocking=False):
        raise HTTPException(429, {"code": "pdf_busy"})
    try:
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > storage.MAX_PDF_BYTES:
                raise HTTPException(413, {"code": "pdf_too_large"})
            data.extend(chunk)
        yield name, title, bytes(data)
    finally:
        upload_slots.release()


def lock_owner(db: DbSession, owner: int):
    if db.scalar(select(User.id).where(User.id == owner).with_for_update(key_share=True)) is None:
        raise HTTPException(401, "Not authenticated")


def matching_pdf(db: DbSession, owner: int, digest: str):
    return db.scalar(select(PdfObject).where(
        PdfObject.charged_user_id == owner, PdfObject.digest == digest,
        or_(PdfObject.user_id == owner, PdfObject.creating.is_(True)),
    ))


def published_material(db: DbSession, pdf: PdfObject | None):
    if pdf is None or not pdf.published:
        return None
    material = db.get(Content, pdf.content_id)
    if material is None:
        return None
    if material.content_type != "pdf":
        raise HTTPException(409, {"code": "pdf_duplicate"})
    return material


def check_category(db: DbSession, owner: int, category_id: int | None, *, lock: bool = False):
    if category_id is not None:
        query = select(Category.id).where(Category.id == category_id, Category.user_id == owner)
        if lock:
            query = query.with_for_update(read=True, key_share=True)
        if db.scalar(query) is None:
            raise HTTPException(404, {"code": "pdf_category_missing"})


@router.get("/pdf", status_code=204)
def availability(_user: CurrentUser):
    require_pdf()
    return Response(status_code=204)


@router.post("/pdf", response_model=ContentOut, status_code=201)
def create_pdf(db: DbSession, user: CurrentUser,
               payload: Annotated[tuple[str, str, bytes], Depends(read_upload)],
               category_id: Annotated[int | None, Query(gt=0, le=MAX_BIGINT)] = None):
    name, title, data = payload
    owner = user.id
    digest = sha256(data).hexdigest()
    # Reserve under the account lock, then publish the card and file in one DB transaction.
    try:
        lock_owner(db, owner)
        pending = matching_pdf(db, owner, digest)
        material = published_material(db, pending)
        if material is not None:
            return material
        check_category(db, owner, category_id)
        db.rollback()
        storage.scan_pdf(data)
        lock_owner(db, owner)
        pending = matching_pdf(db, owner, digest)
        material = published_material(db, pending)
        if material is not None:
            return material
        if pending is None:
            count, size = db.execute(select(func.count(), func.coalesce(func.sum(PdfObject.size_bytes), 0)).where(
                PdfObject.charged_user_id == owner,
            )).one()
            if count >= storage.MAX_PDF_COUNT or size + len(data) > storage.MAX_ACCOUNT_BYTES:
                raise HTTPException(409, {"code": "pdf_quota"})
            pending = PdfObject(id=uuid4(), charged_user_id=owner, digest=digest,
                                name=name, size_bytes=len(data), creating=True)
            db.add(pending)
        object_id = pending.id
        db.commit()

        lock_owner(db, owner)
        pending = db.scalar(select(PdfObject).where(
            PdfObject.id == object_id, PdfObject.charged_user_id == owner,
        ).with_for_update().execution_options(populate_existing=True))
        material = published_material(db, pending)
        if material is not None:
            return material
        if pending is None or not pending.creating:
            raise HTTPException(409, {"code": "pdf_removed"})
        check_category(db, owner, category_id, lock=True)
        storage.put_pdf(pending.id, data)
        material = Content(user_id=owner, title=title, category_id=category_id, content_type="pdf", source="other")
        db.add(material)
        db.flush()
        pending.user_id = owner
        pending.content_id = material.id
        pending.published = True
        pending.creating = False
        db.commit()
        record_activity(db, user)
        return material
    except storage.InvalidPdf as error:
        raise HTTPException(422, {"code": str(error)}) from None
    except storage.PdfServiceUnavailable:
        raise HTTPException(503, {"code": "pdf_service_unavailable"}) from None


@router.get("/contents/{content_id}/pdf", response_model=PdfMetadata)
def read_metadata(content_id: TargetId, db: DbSession, user: CurrentUser):
    item = owned_pdf(db, user.id, content_id)
    if item is None or not item.published:
        raise HTTPException(404, {"code": "pdf_missing"})
    return item


@router.get("/contents/{content_id}/pdf/download", response_class=Response)
def download(content_id: TargetId, db: DbSession, user: CurrentUser):
    item = read_metadata(content_id, db, user)
    object_id, filename, size, digest = item.id, item.name, item.size_bytes, item.digest
    db.rollback()
    if not download_slots.acquire(blocking=False):
        raise HTTPException(429, {"code": "pdf_busy"})
    try:
        data = storage.get_pdf(object_id, size)
        if sha256(data).hexdigest() != digest:
            raise storage.PdfServiceUnavailable
    except storage.PdfServiceUnavailable:
        raise HTTPException(503, {"code": "pdf_service_unavailable"}) from None
    finally:
        download_slots.release()
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=document.pdf; filename*=UTF-8''{quote(filename, safe='')}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    })

