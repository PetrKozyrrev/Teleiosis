import ipaddress
import logging
import re
import socket
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx2

from app.urls import detect_source, normalize_url

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; TeleiosisBot/0.1)"
MAX_BYTES = 512 * 1024
MAX_REDIRECTS = 3
TOTAL_TIMEOUT = 6.0
ALLOWED_PORTS = {None, 80, 443}
REDIRECT_CODES = {301, 302, 303, 307, 308}
HTML_TYPES = {"text/html", "application/xhtml+xml"}
TITLE_MAX = 300
DESCRIPTION_MAX = 1000
IMAGE_URL_MAX = 2048


@dataclass
class Metadata:
    title: str | None = None
    description: str | None = None
    image_url: str | None = None


class UnsafeUrl(Exception):
    """Адрес нельзя открывать с сервера (защита от SSRF)."""


def resolve_ips(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def ensure_public(url: str) -> None:
    """Бросает UnsafeUrl, если по адресу нельзя безопасно ходить."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrl("scheme")
    try:
        port = parts.port
    except ValueError:
        raise UnsafeUrl("port")
    if port not in ALLOWED_PORTS:
        raise UnsafeUrl("port")
    host = parts.hostname
    if not host:
        raise UnsafeUrl("host")

    try:
        addresses = resolve_ips(host, port or (443 if parts.scheme == "https" else 80))
    except OSError:
        raise UnsafeUrl("dns")
    if not addresses:
        raise UnsafeUrl("dns")

    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise UnsafeUrl("non-public address")


def _clean(text, limit: int) -> str | None:
    if not isinstance(text, str):
        return None
    text = " ".join(text.split())
    return text[:limit] or None


class _HeadParser(HTMLParser):
    """Собирает <meta> и <title>, останавливается на </head>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self._title_done = False
        self.finished = False

    def handle_starttag(self, tag, attrs):
        if self.finished:
            return
        if tag == "meta":
            values = {k.lower(): v for k, v in attrs if v is not None}
            key = (values.get("property") or values.get("name") or "").lower()
            if key and "content" in values:
                self.meta.setdefault(key, values["content"])
        elif tag == "title" and not self._title_done:
            self._in_title = True

    def handle_data(self, data):
        if self._in_title and not self.finished:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self._title_done = True
        elif tag == "head":
            self.finished = True


def parse_metadata(html: str, base_url: str) -> Metadata:
    parser = _HeadParser()
    parser.feed(html)
    parser.close()
    meta = parser.meta

    title = _clean(
        meta.get("og:title") or meta.get("twitter:title") or parser.title, TITLE_MAX
    )
    description = _clean(
        meta.get("og:description")
        or meta.get("description")
        or meta.get("twitter:description"),
        DESCRIPTION_MAX,
    )

    image_url = None
    image = meta.get("og:image") or meta.get("twitter:image")
    if image and image.strip():
        try:
            candidate = urljoin(base_url, image.strip())
            if (
                urlsplit(candidate).scheme in ("http", "https")
                and len(candidate) <= IMAGE_URL_MAX
            ):
                image_url = candidate
        except ValueError:
            pass
    return Metadata(title=title, description=description, image_url=image_url)


def _decode(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    else:
        sniff = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
        encoding = sniff.group(1).decode("ascii") if sniff else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _read_html(client, url: str, deadline: float):
    """Скачивает HTML, вручную проверяя каждый редирект.
    Возвращает (итоговый адрес, байты, content-type) или None."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if time.monotonic() > deadline:
            return None
        ensure_public(current)
        with client.stream("GET", current) as response:
            if response.status_code in REDIRECT_CODES:
                location = response.headers.get("location")
                if not location:
                    return None
                current = urljoin(current, location)
                continue
            if response.status_code != 200:
                return None
            content_type = response.headers.get("content-type", "")
            if content_type.split(";")[0].strip().lower() not in HTML_TYPES:
                return None
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) >= MAX_BYTES or time.monotonic() > deadline:
                    break
            return current, bytes(body[:MAX_BYTES]), content_type
    return None


def _youtube(client, url: str) -> Metadata | None:
    response = client.get(
        "https://www.youtube.com/oembed",
        params={"url": normalize_url(url), "format": "json"},
    )
    if response.status_code != 200:
        return None
    data = response.json()
    if not isinstance(data, dict):
        return None
    thumbnail = data.get("thumbnail_url")
    if not (
        isinstance(thumbnail, str)
        and thumbnail.startswith("https://")
        and len(thumbnail) <= IMAGE_URL_MAX
    ):
        thumbnail = None
    return Metadata(title=_clean(data.get("title"), TITLE_MAX), image_url=thumbnail)


def fetch_metadata(url: str, *, transport=None) -> Metadata | None:
    """Best-effort: при любой ошибке возвращает None и не бросает исключений.
    transport нужен только тестам."""
    deadline = time.monotonic() + TOTAL_TIMEOUT
    try:
        with httpx2.Client(
            transport=transport,
            follow_redirects=False,
            timeout=httpx2.Timeout(4.0, connect=3.0),
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ru,en;q=0.8",
            },
        ) as client:
            source, _ = detect_source(url)
            if source == "youtube":
                return _youtube(client, url)
            page = _read_html(client, url, deadline)
            if page is None:
                return None
            final_url, body, content_type = page
            return parse_metadata(_decode(body, content_type), final_url)
    except Exception as exc:  # намеренно широко: загрузка не должна ломать сохранение
        logger.info("metadata fetch failed: %s", type(exc).__name__)
        return None