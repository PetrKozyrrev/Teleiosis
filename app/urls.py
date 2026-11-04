from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
TRACKING_PARAMS = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "igshid"}


class InvalidUrl(ValueError):
    pass


def clean_url(raw: str) -> str:
    """Проверяет ссылку и при необходимости добавляет https://.
    Возвращает ссылку в том виде, в каком её введёт пользователь (без нормализации)."""
    url = raw.strip()
    if not url:
        raise InvalidUrl("URL is empty")
    if len(url) > MAX_URL_LENGTH:
        raise InvalidUrl("URL is too long")
    if any(ch.isspace() for ch in url):
        raise InvalidUrl("URL must not contain spaces")
    if "://" not in url:
        url = "https://" + url

    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise InvalidUrl("Only http and https links are supported")
    if parts.username or parts.password:
        raise InvalidUrl("URL must not contain credentials")
    host = parts.hostname
    if not host or "." not in host:
        raise InvalidUrl("URL has no valid host")
    try:
        parts.port  # проверка корректности порта
    except ValueError:
        raise InvalidUrl("URL has an invalid port")
    return url


def _is_tracking(name: str) -> bool:
    name = name.lower()
    return name.startswith("utm_") or name in TRACKING_PARAMS


def normalize_url(url: str) -> str:
    """Единый вид ссылки для поиска дублей."""
    parts = urlsplit(clean_url(url))
    host = parts.hostname.removeprefix("www.")
    port = parts.port
    path = parts.path
    query = parse_qsl(parts.query, keep_blank_values=True)

    if host == "youtu.be":
        video_id = path.strip("/").split("/")[0]
        if video_id:
            host, path, query = "youtube.com", "/watch", [("v", video_id)]
    elif host in ("youtube.com", "m.youtube.com"):
        host = "youtube.com"
        query = [(k, v) for k, v in query if k in ("v", "list")]
    elif host in ("t.me", "telegram.me"):
        host = "t.me"
        query = []
    else:
        query = [(k, v) for k, v in query if not _is_tracking(k)]

    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = path.rstrip("/")
    return urlunsplit(("https", netloc, path, urlencode(sorted(query)), ""))


def detect_source(url: str) -> tuple[str, str]:
    """Возвращает (source, content_type)."""
    host = urlsplit(normalize_url(url)).hostname
    if host == "youtube.com":
        return "youtube", "video"
    if host == "t.me":
        return "telegram", "post"
    return "web", "article"