from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.deps import DbSession
from app.routers import (
    account, auth, categories, contents, email_verification, password_reset,
    reminders, stats, unsubscribe, users, mobile_auth, app_links, push_devices, organization, library_import, pdf, week_plan, review,
)

# Путь строится от файла, а не от текущей папки: сервер можно запускать откуда угодно
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

WEB_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    # Браузер каждый раз сверяется с сервером (ETag), поэтому правки видны сразу
    "Cache-Control": "no-cache",
}

def create_app() -> FastAPI:
    """Production не публикует OpenAPI; локальная документация сохраняется."""
    production = settings.app_env != "dev"
    application = FastAPI(
        title="Teleiosis API",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/mobile/") or "authorization" in request.headers:
            # Validation errors must not echo passwords or one-time tokens.
            errors = [{"loc": item["loc"], "type": item["type"], "msg": item["msg"]} for item in exc.errors()]
            return JSONResponse({"detail": errors}, status_code=422, headers={"Cache-Control": "no-store"})
        return await request_validation_exception_handler(request, exc)

    @application.middleware("http")
    async def add_web_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/mobile/") or "authorization" in request.headers:
            response.headers["Cache-Control"] = "no-store"
        if path == "/app" or path.startswith("/app/"):
            response.headers.update(WEB_HEADERS)
        return response

    for router in (
        users.router, auth.router, password_reset.router, categories.router,
        contents.router, email_verification.router, account.router, stats.router, push_devices.router,
        unsubscribe.router, reminders.router, mobile_auth.router, app_links.router,
    ):
        application.include_router(router)

    for router in (organization.tags_router, organization.collections_router, organization.router):
        application.include_router(router)
        application.include_router(router, prefix="/mobile/library")
    application.include_router(library_import.router, prefix="/mobile/library")
    application.include_router(contents.search_router, prefix="/mobile/library")
    application.include_router(pdf.router, prefix="/mobile/library")
    application.include_router(week_plan.router)
    application.include_router(review.router)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.get("/ready", include_in_schema=False)
    def ready(db: DbSession):
        # Не раскрывать текст ошибки БД/адрес сервера в публичном ответе.
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                {"status": "unavailable"}, status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse({"status": "ready"}, headers={"Cache-Control": "no-store"})

    @application.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app/")

    application.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return application


app = create_app()
