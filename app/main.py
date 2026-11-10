from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routers import account, auth, categories, contents, email_verification, password_reset, users

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

app = FastAPI(title="Teleiosis API")


@app.middleware("http")
async def add_web_headers(request: Request, call_next):
    """Заголовки безопасности только для сайта (/app). API и /docs их не получают:
    Swagger загружает скрипты с CDN, и CSP его сломала бы."""
    response = await call_next(request)
    path = request.url.path
    if path == "/app" or path.startswith("/app/"):
        response.headers.update(WEB_HEADERS)
    return response


app.include_router(users.router)
app.include_router(auth.router)
app.include_router(password_reset.router)
app.include_router(categories.router)
app.include_router(contents.router)
app.include_router(email_verification.router)
app.include_router(account.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


# Монтируется последним: страницы не перекрывают пути API
app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")