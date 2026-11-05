import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.api import ApiClient, ApiError
from bot.keyboards import (
    MAX_CATEGORY_BUTTONS,
    STATUS_CODES,
    STATUS_LABELS,
    BackCb,
    CategoryMenuCb,
    CategoryPickCb,
    StatusCb,
    category_keyboard,
    main_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()

UNAVAILABLE = "Сервис временно недоступен. Попробуйте чуть позже."
NOT_FOUND = "Материал не найден. Возможно, он был удалён."


async def set_markup(callback: CallbackQuery, markup: InlineKeyboardMarkup | None) -> None:
    """Меняет кнопки под сообщением (None убирает их)."""
    message = callback.message
    if not isinstance(message, Message):
        return  # сообщение слишком старое или недоступно
    try:
        await message.edit_reply_markup(reply_markup=markup)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc):
            logger.warning("edit markup failed: %s", exc)


@router.callback_query(StatusCb.filter())
async def on_status(
    callback: CallbackQuery, callback_data: StatusCb, api: ApiClient
) -> None:
    status = STATUS_CODES.get(callback_data.code)
    if status is None or callback_data.content_id <= 0:
        await callback.answer("Неизвестное действие")
        return
    user = callback.from_user
    try:
        content = await api.update_content(
            user.id, user.username, callback_data.content_id, {"status": status}
        )
    except ApiError as exc:
        logger.warning("status update failed: %s", exc)
        await callback.answer(UNAVAILABLE, show_alert=True)
        return
    if content is None:
        await callback.answer(NOT_FOUND, show_alert=True)
        await set_markup(callback, None)
        return
    await callback.answer(f"Статус: {STATUS_LABELS[status]}")
    await set_markup(callback, main_keyboard(content["id"], content["status"]))


@router.callback_query(CategoryMenuCb.filter())
async def on_category_menu(
    callback: CallbackQuery, callback_data: CategoryMenuCb, api: ApiClient
) -> None:
    if callback_data.content_id <= 0:
        await callback.answer("Неизвестное действие")
        return
    user = callback.from_user
    try:
        categories = await api.list_categories(user.id, user.username)
    except ApiError as exc:
        logger.warning("list categories failed: %s", exc)
        await callback.answer(UNAVAILABLE, show_alert=True)
        return
    if not categories:
        await callback.answer(
            "Категорий пока нет. Создайте первую: /category Название",
            show_alert=True,
        )
        return
    note = None
    if len(categories) > MAX_CATEGORY_BUTTONS:
        note = f"Показаны первые {MAX_CATEGORY_BUTTONS} категорий"
    await callback.answer(note)
    await set_markup(callback, category_keyboard(callback_data.content_id, categories))


@router.callback_query(CategoryPickCb.filter())
async def on_category_pick(
    callback: CallbackQuery, callback_data: CategoryPickCb, api: ApiClient
) -> None:
    if callback_data.content_id <= 0 or callback_data.category_id < 0:
        await callback.answer("Неизвестное действие")
        return
    category_id = callback_data.category_id or None  # 0 = убрать категорию
    user = callback.from_user
    try:
        content = await api.update_content(
            user.id,
            user.username,
            callback_data.content_id,
            {"category_id": category_id},
        )
    except ApiError as exc:
        logger.warning("category update failed: %s", exc)
        await callback.answer(UNAVAILABLE, show_alert=True)
        return
    if content is None:
        await callback.answer(
            "Не получилось: материал или категория не найдены.", show_alert=True
        )
        return
    await callback.answer("Категория назначена" if category_id else "Категория убрана")
    await set_markup(callback, main_keyboard(content["id"], content["status"]))


@router.callback_query(BackCb.filter())
async def on_back(
    callback: CallbackQuery, callback_data: BackCb, api: ApiClient
) -> None:
    if callback_data.content_id <= 0:
        await callback.answer("Неизвестное действие")
        return
    user = callback.from_user
    content = await api.get_content(user.id, user.username, callback_data.content_id)
    await callback.answer()
    status = content["status"] if content else None
    await set_markup(callback, main_keyboard(callback_data.content_id, status))