import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from bot import callbacks, handlers
from bot.api import ApiClient
from bot.config import settings

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан в .env")
    if len(settings.bot_api_key) < 32:
        raise SystemExit("BOT_API_KEY не задан или короче 32 символов в .env")

    api = ApiClient(settings.api_base_url, settings.bot_api_key)
    session = AiohttpSession(proxy=settings.telegram_proxy or None)
    if settings.telegram_proxy:
        # Сам адрес не логируем: в нём может быть пароль
        logger.info("Запросы к Telegram идут через прокси")
    bot = Bot(token=settings.bot_token, session=session)
    dp = Dispatcher(api=api)  # api доступен в обработчиках по имени
    dp.include_router(handlers.router)
    dp.include_router(callbacks.router)
    try:
        await dp.start_polling(bot)
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())