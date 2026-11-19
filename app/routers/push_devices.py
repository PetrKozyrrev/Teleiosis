"""Native registration is opt-in and belongs to the current mobile session."""
from datetime import datetime, timezone
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import delete, func, select

from app.config import settings
from app.deps import CurrentUser, DbSession
from app.models import AuthSession, PushDevice
from app.routers.mobile_auth import native_request
from app.sessions import hash_token

router = APIRouter(prefix="/mobile/devices", dependencies=[Depends(native_request)])


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=4096, pattern=r"^[!-~]+$")
    enabled: StrictBool


@router.put("/{installation_id}")
def register(installation_id: UUID, data: Registration, request: Request, db: DbSession, user: CurrentUser):
    if not settings.push_enabled:
        raise HTTPException(503, "Push is not configured")
    session = db.scalar(select(AuthSession).where(
        AuthSession.token_hash == hash_token(request.headers["authorization"].split(" ")[1]),
        AuthSession.client_type == "mobile", AuthSession.user_id == user.id,
    ))
    if session is None:
        raise HTTPException(401, "Not authenticated")
    # Registration is infrequent; one short lock also serializes token transfers.
    db.execute(select(func.pg_advisory_xact_lock(7_000_002)))
    fingerprint = sha256(data.token.encode()).hexdigest()
    current = db.get(PushDevice, installation_id)
    if current is not None and current.user_id != user.id:
        raise HTTPException(409, "Use a separate installation identifier for this account")
    duplicates = db.scalars(select(PushDevice).where(
        PushDevice.token_hash == fingerprint, PushDevice.id != installation_id
    )).all()
    for duplicate in duplicates:
        db.delete(duplicate)
    db.flush()
    if current is None:
        count = db.scalar(select(func.count()).select_from(PushDevice).where(PushDevice.user_id == user.id))
        if count >= 10:
            raise HTTPException(409, "Too many registered devices")
        current = PushDevice(id=installation_id, enabled=False, enabled_at=datetime.now(timezone.utc))
        db.add(current)
    if current.session_id != session.id or not current.enabled and data.enabled:
        current.enabled_at = datetime.now(timezone.utc)
    current.user_id = user.id
    current.session_id = session.id
    current.token = data.token
    current.token_hash = fingerprint
    current.enabled = data.enabled
    db.commit()
    return {"id": current.id, "enabled": current.enabled}


@router.delete("/{installation_id}", status_code=204)
def unregister(installation_id: UUID, db: DbSession, user: CurrentUser):
    db.execute(delete(PushDevice).where(PushDevice.id == installation_id, PushDevice.user_id == user.id))
    db.commit()
    return Response(status_code=204)
