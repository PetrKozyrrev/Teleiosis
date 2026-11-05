import re

from aiogram.types import MessageEntity

MAX_LINKS = 5
TITLE_MAX = 100
# Имя публичного канала в Telegram: латиница, цифры, _, 5-32 символа, начинается с буквы
CHANNEL_USERNAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")


def _slice_utf16(text: str, offset: int, length: int) -> str:
    """Telegram считает позиции в единицах UTF-16 (эмодзи занимает две)."""
    data = text.encode("utf-16-le")
    return data[offset * 2 : (offset + length) * 2].decode("utf-16-le", errors="ignore")


def extract_urls(text: str | None, entities: list[MessageEntity] | None) -> list[str]:
    """Ссылки из сообщения в порядке появления, без повторов."""
    if not text or not entities:
        return []
    found: list[str] = []
    for entity in entities:
        if entity.type == "url":
            url = _slice_utf16(text, entity.offset, entity.length)
        elif entity.type == "text_link" and entity.url:
            url = entity.url
        else:
            continue
        url = url.strip()
        if url and url not in found:
            found.append(url)
    return found


def channel_post_url(username: str | None, message_id: int | None) -> str | None:
    """Адрес поста публичного канала или None, если данные не подходят."""
    if not username or not CHANNEL_USERNAME_RE.fullmatch(username):
        return None
    if not isinstance(message_id, int) or message_id <= 0:
        return None
    return f"https://t.me/{username}/{message_id}"


def post_title(text: str | None, channel: str) -> str:
    """Название поста: первая непустая строка текста, иначе «Пост из @канал»."""
    first_line = next(
        (line.strip() for line in (text or "").splitlines() if line.strip()), ""
    )
    return first_line[:TITLE_MAX] if first_line else f"Пост из @{channel}"