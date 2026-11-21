from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.deps import CurrentUser, DbSession
from app.library_import import FILE_LIMIT, GroupQuotaError, ImportSummary, InvalidExport, import_library, validate_export
from app.models import User

router = APIRouter(prefix="/imports", tags=["library import"])


async def read_export(request: Request, _user: CurrentUser) -> bytes:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(415, {"code": "json_required"})
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > FILE_LIMIT:
            raise HTTPException(413, {"code": "file_too_large"})
        raw.extend(chunk)
    return bytes(raw)


@router.post("/{mode}", response_model=ImportSummary)
def run_import(mode: Literal["preview", "apply"], db: DbSession, user: CurrentUser,
               raw: Annotated[bytes, Depends(read_export)]):
    try:
        data = validate_export(raw)
        if mode == "apply":
            # Serialize imports and organization writes while allowing unrelated FK inserts.
            db.execute(select(User.id).where(User.id == user.id).with_for_update(key_share=True)).one()
        return import_library(db, user.id, data, apply=mode == "apply")
    except InvalidExport as error:
        raise HTTPException(422, {"code": error.code, "location": error.location}) from None
    except GroupQuotaError:
        raise HTTPException(409, {"code": "group_limit_reached"}) from None
    except DBAPIError as error:
        db.rollback()
        if isinstance(error, IntegrityError) or getattr(error.orig, "sqlstate", None) in {"40P01", "40001", "54000"}:
            raise HTTPException(409, {"code": "import_conflict"}) from None
        raise
