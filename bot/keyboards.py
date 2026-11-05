from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Короткий код в callback_data -> статус в API
STATUS_CODES = {"p": "planned", "s": "studied", "i": "irrelevant"}
STATUS_LABELS = {
    "planned": "Запланировано",
    "studied": "Изучено",
    "irrelevant": "Неактуально",
}
MAX_CATEGORY_BUTTONS = 8
CATEGORY_LABEL_MAX = 30


class StatusCb(CallbackData, prefix="st"):
    content_id: int
    code: str


class CategoryMenuCb(CallbackData, prefix="cm"):
    content_id: int


class CategoryPickCb(CallbackData, prefix="cp"):
    content_id: int
    category_id: int  # 0 = убрать категорию


class BackCb(CallbackData, prefix="bk"):
    content_id: int


def main_keyboard(content_id: int, status: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки под сохранённым материалом. Текущий статус отмечен галочкой."""

    def status_button(code: str) -> InlineKeyboardButton:
        name = STATUS_CODES[code]
        mark = "✓ " if name == status else ""
        return InlineKeyboardButton(
            text=mark + STATUS_LABELS[name],
            callback_data=StatusCb(content_id=content_id, code=code).pack(),
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [status_button("p"), status_button("s")],
            [
                status_button("i"),
                InlineKeyboardButton(
                    text="📁 Категория",
                    callback_data=CategoryMenuCb(content_id=content_id).pack(),
                ),
            ],
        ]
    )


def _label(name: str) -> str:
    if len(name) <= CATEGORY_LABEL_MAX:
        return name
    return name[: CATEGORY_LABEL_MAX - 1] + "…"


def category_keyboard(content_id: int, categories: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=_label(category["name"]),
            callback_data=CategoryPickCb(
                content_id=content_id, category_id=category["id"]
            ).pack(),
        )
        for category in categories[:MAX_CATEGORY_BUTTONS]
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="Без категории",
                callback_data=CategoryPickCb(
                    content_id=content_id, category_id=0
                ).pack(),
            ),
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=BackCb(content_id=content_id).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)