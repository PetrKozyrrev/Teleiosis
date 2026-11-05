import asyncio

from bot.api import SaveResult
from bot.handlers import describe_note, describe_save, shorten


class StubApi:
    def __init__(self, result, existing=None):
        self.result = result
        self.existing = existing
        self.calls = []

    async def save_url(self, telegram_id, username, url, title=None, note=None):
        self.calls.append(("url", url, title, note))
        return self.result

    async def save_note(self, telegram_id, username, text):
        self.calls.append(("note", text))
        return self.result

    async def get_content(self, telegram_id, username, content_id):
        return self.existing


def describe(api, url="https://example.com/a", **kwargs):
    return asyncio.run(describe_save(api, 1, None, url, **kwargs))


def test_saved_message_contains_title():
    text = describe(StubApi(SaveResult("saved", content={"title": "Название"})))
    assert text.startswith("✅")
    assert "Название" in text


def test_duplicate_message_shows_existing_title():
    api = StubApi(SaveResult("duplicate", existing_id=3), existing={"title": "Старое"})
    text = describe(api)
    assert text.startswith("ℹ️")
    assert "Старое" in text


def test_duplicate_without_title_has_generic_message():
    text = describe(StubApi(SaveResult("duplicate", existing_id=3), existing=None))
    assert "уже есть" in text


def test_invalid_message():
    text = describe(StubApi(SaveResult("invalid")), url="http://bad")
    assert text.startswith("⚠️")
    assert "http://bad" in text


def test_title_and_note_are_passed_to_api():
    api = StubApi(SaveResult("saved", content={"title": "Заголовок"}))
    describe(api, "https://t.me/durov/1", title="Заголовок", note="Текст")
    assert api.calls == [("url", "https://t.me/durov/1", "Заголовок", "Текст")]


def test_note_saved_message():
    api = StubApi(
        SaveResult("saved", content={"title": "Идея", "content_type": "note"})
    )
    text = asyncio.run(describe_note(api, 1, None, "Идея про рассылку"))
    assert text.startswith("📝")
    assert "Идея" in text
    assert api.calls == [("note", "Идея про рассылку")]


def test_note_invalid_message():
    text = asyncio.run(describe_note(StubApi(SaveResult("invalid")), 1, None, "x"))
    assert text.startswith("⚠️")


def test_shorten():
    assert shorten("коротко") == "коротко"
    long = shorten("a" * 200, 100)
    assert len(long) == 100
    assert long.endswith("…")