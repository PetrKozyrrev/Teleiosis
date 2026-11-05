import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.api import ApiClient, ApiError
from bot.links import MAX_LINKS, extract_urls

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private")  # только личные чаты


def shorten(text: str, limit: int = 100) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def describe_save(
    api: ApiClient, telegram_id: int, username: str | None, url: str
) -> str:
    """Сохраняет одну ссылку и возвращает строку для ответа пользователю."""
    result = await api.save_url(telegram_id, username, url)

    if result.status == "saved":
        return f"✅ Сохранено: {shorten(result.content['title'])}"

    if result.status == "duplicate":
        existing = None
        if result.existing_id is not None:
            existing = await api.get_content(telegram_id, username, result.existing_id)
        if existing:
            return f"ℹ️ Уже в библиотеке: {shorten(existing['title'])}"
        return "ℹ️ Эта ссылка уже есть в вашей библиотеке."

    return f"⚠️ Не удалось сохранить, ссылка выглядит некорректно: {shorten(url, 60)}"


@router.message(CommandStart())
async def start(message: Message, api: ApiClient) -> None:
    user = message.from_user
    if user is None:
        return
    try:
        await api.register(user.id, user.username)
    except ApiError as exc:
        logger.warning("register failed: %s", exc)
        await message.answer("Сервис временно недоступен. Попробуйте чуть позже.")
        return
    await message.answer(
        "Привет! Я Teleiosis, помощник, который хранит ваши полезные материалы.\n"
        "Вы зарегистрированы. Пришлите мне ссылку на видео, пост или статью, "
        "и я сохраню её в вашей библиотеке."
    )


@router.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message, api: ApiClient, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return

    urls = extract_urls(message.text, message.entities)
    if not urls:
        await message.answer("Пришлите ссылку на видео, пост или статью, и я сохраню её.")
        return

    skipped = max(0, len(urls) - MAX_LINKS)
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    lines: list[str] = []
    for url in urls[:MAX_LINKS]:
        try:
            lines.append(await describe_save(api, user.id, user.username, url))
        except ApiError as exc:
            logger.warning("save failed: %s", exc)
            lines.append("⚠️ Сервис временно недоступен. Попробуйте чуть позже.")
            break  # если API лежит, остальные ссылки не пробуем
    if skipped:
        lines.append(f"Обработаны первые {MAX_LINKS} ссылок, ещё {skipped} пропущено.")

    await message.answer("\n".join(lines))