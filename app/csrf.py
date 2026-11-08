"""Защита от CSRF: изменяющий запрос по cookie принимается только со своего сайта.

Правило: если есть заголовок Origin, он должен точно совпасть с APP_ORIGIN.
Иначе смотрим Sec-Fetch-Site (допустимы same-origin и none). Нет ни того,
ни другого: отказ. Браузер всегда присылает Origin с POST, PUT, PATCH, DELETE.
"""

from fastapi import HTTPException, Request, status

from app.config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SAME_SITE_VALUES = {"same-origin", "none"}


def check_same_origin(request: Request) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is not None:
        allowed = origin == settings.app_origin
    else:
        allowed = request.headers.get("sec-fetch-site") in SAME_SITE_VALUES
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request rejected")


def require_same_origin(request: Request) -> None:
    """Зависимость для эндпоинтов, которые проверяют Origin всегда."""
    check_same_origin(request)