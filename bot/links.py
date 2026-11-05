from aiogram.types import MessageEntity

MAX_LINKS = 5


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