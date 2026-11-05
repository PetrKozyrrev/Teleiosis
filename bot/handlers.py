import logging
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot.api import ApiClient, ApiError, SaveResult
from bot.keyboards import main_keyboard
from bot.links import MAX_LINKS, channel_post_url, extract_urls, post_title

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private")  # только личные чаты

UNAVAILABLE = "⚠️ Сервис временно недоступен. Попробуйте чуть позже."
HELP_TEXT = (
    "Я умею сохранять:\n"
    "• ссылки: просто пришлите их;\n"
    "• пересланные посты и сообщения;\n"
    "• текстовые заметки: /note ваш текст\n\n"
    "Категории: /category Название создаёт новую. "
    "Назначить её материалу можно кнопкой под сохранённым сообщением."
)


@dataclass
class Outcome:
    """Результат сохранения одного материала."""

    text: str
    content_id: int | None = None  # если задан, под ответом показываем кнопки
    status: str | None = None


def shorten(text: str, limit: int = 100) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def reply(message: Message, text: str, outcome: Outcome | None = None) -> None:
    markup = None
    if outcome is not None and outcome.content_id is not None:
        markup = main_keyboard(outcome.content_id, outcome.status)
    await message.answer(text, reply_markup=markup)


async def describe_result(
    api: ApiClient,
    telegram_id: int,
    username: str | None,
    result: SaveResult,
    invalid_text: str,
) -> Outcome:
    """Превращает результат сохранения в текст ответа и данные для кнопок."""
    if result.status == "saved":
        content = result.content or {}
        title = shorten(content.get("title", ""))
        if content.get("content_type") == "note":
            text = f"📝 Заметка сохранена: {title}"
        else:
            text = f"✅ Сохранено: {title}"
        return Outcome(text, content.get("id"), content.get("status"))

    if result.status == "duplicate":
        existing = None
        if result.existing_id is not None:
            existing = await api.get_content(telegram_id, username, result.existing_id)
        if existing:
            return Outcome(
                f"ℹ️ Уже в библиотеке: {shorten(existing['title'])}",
                result.existing_id,
                existing.get("status"),
            )
        return Outcome("ℹ️ Эта ссылка уже есть в вашей библиотеке.", result.existing_id)

    return Outcome(invalid_text)


async def describe_save(
    api: ApiClient,
    telegram_id: int,
    username: str | None,
    url: str,
    title: str | None = None,
    note: str | None = None,
) -> Outcome:
    """Сохраняет одну ссылку (при необходимости с названием и заметкой)."""
    result = await api.save_url(telegram_id, username, url, title=title, note=note)
    return await describe_result(
        api,
        telegram_id,
        username,
        result,
        f"⚠️ Не удалось сохранить, ссылка выглядит некорректно: {shorten(url, 60)}",
    )


async def describe_note(
    api: ApiClient, telegram_id: int, username: str | None, text: str
) -> Outcome:
    result = await api.save_note(telegram_id, username, text)
    return await describe_result(
        api, telegram_id, username, result, "⚠️ Не удалось сохранить заметку."
    )


async def save_links(
    api: ApiClient, telegram_id: int, username: str | None, urls: list[str]
) -> tuple[str, Outcome | None]:
    """Сохраняет до MAX_LINKS ссылок. Возвращает текст ответа и, если ссылка
    была ровно одна, её результат (для кнопок)."""
    lines: list[str] = []
    outcomes: list[Outcome] = []
    for url in urls[:MAX_LINKS]:
        try:
            outcome = await describe_save(api, telegram_id, username, url)
        except ApiError as exc:
            logger.warning("save failed: %s", exc)
            lines.append(UNAVAILABLE)
            break  # если API лежит, остальные ссылки не пробуем
        lines.append(outcome.text)
        outcomes.append(outcome)
    skipped = len(urls) - MAX_LINKS
    if skipped > 0:
        lines.append(f"Обработаны первые {MAX_LINKS} ссылок, ещё {skipped} пропущено.")
    single = outcomes[0] if len(urls) == 1 and len(outcomes) == 1 else None
    return "\n".join(lines), single


def forwarded_channel(message: Message) -> tuple[str, str] | None:
    """(имя канала, адрес поста), если сообщение переслано из публичного канала."""
    origin = message.forward_origin
    if origin is None or origin.type != "channel":
        return None
    channel_name = origin.chat.username
    url = channel_post_url(channel_name, origin.message_id)
    return (channel_name, url) if url else None


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
        "Вы зарегистрированы.\n\n" + HELP_TEXT
    )


@router.message(Command("note"))
async def note(message: Message, command: CommandObject, api: ApiClient) -> None:
    user = message.from_user
    if user is None:
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer(
            "Напишите заметку после команды, например:\n"
            "/note Проверить идею про рассылку"
        )
        return
    try:
        outcome = await describe_note(api, user.id, user.username, text)
    except ApiError as exc:
        logger.warning("save failed: %s", exc)
        await message.answer(UNAVAILABLE)
        return
    await reply(message, outcome.text, outcome)


@router.message(Command("category"))
async def category(message: Message, command: CommandObject, api: ApiClient) -> None:
    user = message.from_user
    if user is None:
        return
    name = (command.args or "").strip()
    if not name:
        await message.answer(
            "Напишите название после команды, например:\n/category Маркетинг"
        )
        return
    try:
        result = await api.create_category(user.id, user.username, name)
    except ApiError as exc:
        logger.warning("create category failed: %s", exc)
        await message.answer(UNAVAILABLE)
        return
    if result.status == "created":
        await message.answer(f"📁 Категория создана: {shorten(name, 50)}")
    elif result.status == "duplicate":
        await message.answer("ℹ️ Такая категория у вас уже есть.")
    else:
        await message.answer("⚠️ Название категории должно быть от 1 до 50 символов.")


@router.message(F.forward_origin)
async def handle_forward(message: Message, api: ApiClient, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return

    text = message.text or message.caption
    entities = message.entities if message.text else message.caption_entities
    channel = forwarded_channel(message)
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    outcome: Outcome | None = None
    try:
        if channel:
            # 1. Пост публичного канала сохраняем как пост
            channel_name, url = channel
            outcome = await describe_save(
                api,
                user.id,
                user.username,
                url,
                title=post_title(text, channel_name),
                note=text,
            )
            answer = outcome.text
        else:
            urls = extract_urls(text, entities)
            if urls:
                # 2. В сообщении есть ссылки: сохраняем их
                answer, outcome = await save_links(api, user.id, user.username, urls)
            elif text:
                # 3. Просто текст: сохраняем заметкой
                outcome = await describe_note(api, user.id, user.username, text)
                answer = outcome.text
            else:
                # 4. Нечего сохранять
                answer = "Из этого сообщения нечего сохранить: в нём нет текста и ссылок."
    except ApiError as exc:
        logger.warning("save failed: %s", exc)
        answer, outcome = UNAVAILABLE, None

    await reply(message, answer, outcome)


@router.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message, api: ApiClient, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return

    urls = extract_urls(message.text, message.entities)
    if not urls:
        await message.answer(
            "Пришлите ссылку, перешлите пост или напишите заметку: /note ваш текст"
        )
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    answer, outcome = await save_links(api, user.id, user.username, urls)
    await reply(message, answer, outcome)


@router.message()
async def handle_other(message: Message) -> None:
    """Всё остальное: стикеры, голосовые, неизвестные команды."""
    await message.answer(HELP_TEXT)