"""Native-only transport over the shared account and credential rules."""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.cookies import cookie_name
from app.deps import CurrentUser, DbSession
from app.models import AuthSession, User
from app.routers import auth, email_verification, password_reset
from app.schemas import EmailVerificationConfirm, LoginRequest, MobileRegisterRequest, PasswordResetConfirm, PasswordResetRequest, UserOut
from app.sessions import SESSION_ABSOLUTE, create_session, delete_session, hash_token


def native_request(request: Request) -> None:
    if cookie_name() in request.cookies:
        raise HTTPException(401, "Mobile authentication does not accept session cookies")
    if "origin" in request.headers or "sec-fetch-site" in request.headers:
        raise HTTPException(403, "Use the browser authentication endpoints")


def anonymous_native_request(request: Request) -> None:
    if "authorization" in request.headers:
        raise HTTPException(401, "Do not send a session when requesting credentials")


router = APIRouter(prefix="/mobile/auth", tags=["mobile-auth"], dependencies=[Depends(native_request)])


class MobileSessionOut(BaseModel):
    user: UserOut
    expires_at: datetime
    absolute_expires_at: datetime


class MobileLoginOut(MobileSessionOut):
    token: str
    token_type: str = "Bearer"


def session_info(db: DbSession, user: User, token: str) -> MobileSessionOut:
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token), AuthSession.client_type == "mobile"))
    if row is None:
        raise HTTPException(401, "Not authenticated")
    return MobileSessionOut(user=UserOut.model_validate(user), expires_at=row.expires_at, absolute_expires_at=row.created_at + SESSION_ABSOLUTE)


def start_mobile_session(db: DbSession, user: User) -> MobileLoginOut:
    token, _ = create_session(db, user, client_type="mobile")
    return MobileLoginOut(**session_info(db, user, token).model_dump(), token=token)


@router.post("/register", response_model=MobileLoginOut, status_code=201, dependencies=[Depends(anonymous_native_request)])
def register(data: MobileRegisterRequest, request: Request, response: Response, db: DbSession):
    response.headers["Cache-Control"] = "no-store"
    return start_mobile_session(db, auth.register_user(data, request, db, display_name=data.display_name))


@router.post("/login", response_model=MobileLoginOut, dependencies=[Depends(anonymous_native_request)])
def login(data: LoginRequest, request: Request, response: Response, db: DbSession):
    response.headers["Cache-Control"] = "no-store"
    return start_mobile_session(db, auth.authenticate_user(data, request, db))


@router.get("/session", response_model=MobileSessionOut)
def current_session(request: Request, response: Response, db: DbSession, user: CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    token = request.headers["authorization"].split(" ")[1]
    return session_info(db, user, token)


@router.post("/logout", status_code=204)
def logout(request: Request, db: DbSession, user: CurrentUser):
    token = request.headers["authorization"].split(" ")[1]
    delete_session(db, token, client_type="mobile")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/password-reset/request", status_code=202, dependencies=[Depends(anonymous_native_request)])
def request_reset(data: PasswordResetRequest, request: Request, response: Response, background_tasks: BackgroundTasks, db: DbSession):
    # The same neutral response, rate-limit buckets and HTTPS web fallback link.
    return password_reset.request_reset(data, request, response, background_tasks, db)


@router.post("/password-reset/confirm", status_code=204, dependencies=[Depends(anonymous_native_request)])
def confirm_reset(data: PasswordResetConfirm, db: DbSession):
    response = password_reset.confirm_reset(data, db)
    # A native response must never create/delete browser credentials.
    if "set-cookie" in response.headers:
        del response.headers["set-cookie"]
    return response


@router.post("/email-verification/request", status_code=202)
def request_verification(request: Request, response: Response, background_tasks: BackgroundTasks, db: DbSession, user: CurrentUser):
    return email_verification.request_verification(request, response, background_tasks, db, user)


@router.post("/email-verification/confirm", status_code=204, dependencies=[Depends(anonymous_native_request)])
def confirm_verification(data: EmailVerificationConfirm, db: DbSession):
    return email_verification.confirm_verification(data, db)
