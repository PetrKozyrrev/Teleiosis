import ipaddress
import json
import logging
import re
import socket
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx2

from app.urls import detect_source, normalize_url

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; TeleiosisBot/0.1)"
MAX_BYTES = 512 * 1024
YOUTUBE_MAX_BYTES = 2 * 1024 * 1024
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
    video_duration_seconds: int | None = None
    text_character_count: int | None = None


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


class _MetadataParser(HTMLParser):
    """Collect head metadata and text in complete article, main or body elements."""

    text_tags = {"article", "main", "body"}
    omitted_tags = {"script", "style", "noscript", "template", "nav", "aside", "footer", "form"}
    text_breaks = text_tags | {"p", "br", "div", "section", "li", "td", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self._title_done = False
        self.finished = False
        self._omitted = 0
        self._depth = dict.fromkeys(self.text_tags, 0)
        self._text: dict[str, list[str]] = {tag: [] for tag in self.text_tags}
        self.character_counts: dict[str, int] = {}

    def handle_starttag(self, tag, attrs):
        if tag in self.text_breaks:
            self.handle_data(" ")
        if tag in self.omitted_tags:
            self._omitted += 1
        if not self._omitted and tag in self.text_tags and tag not in self.character_counts:
            self._depth[tag] += 1
        if tag == "meta" and not self.finished:
            values = {k.lower(): v for k, v in attrs if v is not None}
            key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            if key and "content" in values:
                self.meta.setdefault(key, values["content"])
        elif tag == "title" and not self.finished and not self._title_done:
            self._in_title = True

    def handle_data(self, data):
        if self._in_title and not self.finished:
            self.title += data
        if not self._omitted:
            for tag, depth in self._depth.items():
                if depth:
                    self._text[tag].append(data)

    def handle_endtag(self, tag):
        if tag in self.omitted_tags and self._omitted:
            self._omitted -= 1
        if not self._omitted and tag in self.text_tags and self._depth[tag]:
            self._depth[tag] -= 1
            if not self._depth[tag]:
                self.character_counts[tag] = len(" ".join("".join(self._text[tag]).split()))
        if tag in self.text_breaks:
            self.handle_data(" ")
        if tag == "title" and self._in_title:
            self._in_title = False
            self._title_done = True
        elif tag == "head":
            self.finished = True


def _duration_seconds(value: object) -> int | None:
    if type(value) is int:
        return value if 0 < value <= 2_147_483_647 else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]{1,10}", value):
        return _duration_seconds(int(value))
    match = re.fullmatch(r"P(?:([0-9]{1,7})D)?(?:T(?:([0-9]{1,7})H)?(?:([0-9]{1,7})M)?(?:([0-9]{1,7})S)?)?", value)
    if not match:
        return None
    days, hours, minutes, seconds = (int(part or "0") for part in match.groups())
    return _duration_seconds(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def parse_metadata(html: str, base_url: str, *, youtube_id: str | None = None) -> Metadata:
    parser = _MetadataParser()
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
    video = youtube_id or meta.get("og:type", "").lower().split(".", 1)[0] == "video"
    duration = None
    if video:
        duration = _duration_seconds(meta.get("video:duration") or meta.get("og:video:duration") or meta.get("duration"))
        if youtube_id:
            duration = _youtube_player_duration(html, youtube_id) or duration
    characters = next((parser.character_counts[tag] for tag in ("article", "main", "body")
                       if parser.character_counts.get(tag)), None)
    return Metadata(title=title, description=description, image_url=image_url,
                    video_duration_seconds=duration, text_character_count=None if video else characters)


def _youtube_player_duration(html: str, video_id: str) -> int | None:
    match = re.search(r"\bytInitialPlayerResponse\s*=\s*(?=\{)", html)
    if not match:
        return None
    try:
        player, _ = json.JSONDecoder().raw_decode(html, match.end())
    except (ValueError, RecursionError):
        return None
    video = player.get("videoDetails")
    if isinstance(video, dict) and video.get("videoId") == video_id and not (video.get("isLive") or video.get("isUpcoming")):
        return _duration_seconds(video.get("lengthSeconds"))
    return None


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


def _read_html(client, url: str, deadline: float, *, byte_limit: int = MAX_BYTES):
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
                if len(body) >= byte_limit or time.monotonic() > deadline:
                    break
            return current, bytes(body[:byte_limit]), content_type
    return None


def _youtube(client, url: str, deadline: float) -> Metadata | None:
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
    result = Metadata(title=_clean(data.get("title"), TITLE_MAX), image_url=thumbnail)
    parts = urlsplit(normalize_url(url))
    video_id = parse_qs(parts.query).get("v", [""])[0] if parts.path == "/watch" else ""
    if parts.path.startswith(("/shorts/", "/live/", "/embed/")):
        video_id = parts.path.split("/")[2]
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        try:
            page = _read_html(client, f"https://www.youtube.com/watch?v={video_id}", deadline,
                              byte_limit=YOUTUBE_MAX_BYTES)
            if page:
                final_url, body, content_type = page
                final = urlsplit(normalize_url(final_url))
                if final.hostname == "youtube.com" and final.path == "/watch" and parse_qs(final.query).get("v") == [video_id]:
                    result.video_duration_seconds = parse_metadata(_decode(body, content_type), final_url,
                                                                   youtube_id=video_id).video_duration_seconds
        except Exception as exc:
            logger.info("video duration fetch failed: %s", type(exc).__name__)
    return result


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
                return _youtube(client, url, deadline)
            page = _read_html(client, url, deadline)
            if page is None:
                return None
            final_url, body, content_type = page
            return parse_metadata(_decode(body, content_type), final_url)
    except Exception as exc:  # намеренно широко: загрузка не должна ломать сохранение
        logger.info("metadata fetch failed: %s", type(exc).__name__)
        return None
