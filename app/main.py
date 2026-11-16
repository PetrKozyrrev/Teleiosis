from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.deps import DbSession
from app.routers import (
    account, auth, categories, contents, email_verification, password_reset,
    reminders, stats, unsubscribe, users,
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
    production = settings.app_env == "prod"
    application = FastAPI(
        title="Teleiosis API",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    @application.middleware("http")
    async def add_web_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/app" or path.startswith("/app/"):
            response.headers.update(WEB_HEADERS)
        return response

    for router in (
        users.router, auth.router, password_reset.router, categories.router,
        contents.router, email_verification.router, account.router, stats.router,
        unsubscribe.router, reminders.router,
    ):
        application.include_router(router)

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
