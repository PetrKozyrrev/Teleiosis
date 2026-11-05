import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.api import ApiClient, ApiError

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private")  # только личные чаты


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
        "Вы зарегистрированы. Сохранение ссылок появится совсем скоро."
    )
    