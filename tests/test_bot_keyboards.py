from bot.keyboards import (
    MAX_CATEGORY_BUTTONS,
    BackCb,
    CategoryMenuCb,
    CategoryPickCb,
    StatusCb,
    category_keyboard,
    main_keyboard,
)

MAX_BIGINT = 9_223_372_036_854_775_807


def buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_callback_data_fits_telegram_limit():
    packed = [
        StatusCb(content_id=MAX_BIGINT, code="s").pack(),
        CategoryMenuCb(content_id=MAX_BIGINT).pack(),
        CategoryPickCb(content_id=MAX_BIGINT, category_id=MAX_BIGINT).pack(),
        BackCb(content_id=MAX_BIGINT).pack(),
    ]
    assert all(len(item.encode()) <= 64 for item in packed)


def test_callback_roundtrip():
    restored = StatusCb.unpack(StatusCb(content_id=12, code="p").pack())
    assert (restored.content_id, restored.code) == (12, "p")


def test_main_keyboard_marks_only_current_status():
    texts = [b.text for b in buttons(main_keyboard(1, "studied"))]
    assert "✓ Изучено" in texts
    assert sum(text.startswith("✓") for text in texts) == 1


def test_main_keyboard_without_status_has_no_mark():
    texts = [b.text for b in buttons(main_keyboard(1, None))]
    assert not any(text.startswith("✓") for text in texts)
    assert {"Запланировано", "Изучено", "Неактуально"} <= set(texts)


def test_main_keyboard_has_category_button():
    assert any(b.text.startswith("📁") for b in buttons(main_keyboard(1)))


def test_category_keyboard_limits_buttons_and_has_clear_and_back():
    categories = [{"id": i, "name": f"Категория {i}"} for i in range(1, 13)]
    items = buttons(category_keyboard(5, categories))
    picks = [b for b in items if b.callback_data.startswith("cp:")]
    assert len(picks) == MAX_CATEGORY_BUTTONS + 1  # категории + «Без категории»
    assert any(b.text == "Без категории" and b.callback_data == "cp:5:0" for b in items)
    assert any(b.callback_data == "bk:5" for b in items)


def test_long_category_name_is_truncated():
    items = buttons(category_keyboard(1, [{"id": 1, "name": "а" * 100}]))
    assert len(items[0].text) == 30