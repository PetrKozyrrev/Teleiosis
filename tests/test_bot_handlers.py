import asyncio

from bot.api import SaveResult
from bot.handlers import describe_save, shorten


class StubApi:
    def __init__(self, result, existing=None):
        self.result = result
        self.existing = existing

    async def save_url(self, telegram_id, username, url):
        return self.result

    async def get_content(self, telegram_id, username, content_id):
        return self.existing


def describe(api, url="https://example.com/a"):
    return asyncio.run(describe_save(api, 1, None, url))


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


def test_shorten():
    assert shorten("коротко") == "коротко"
    long = shorten("a" * 200, 100)
    assert len(long) == 100
    assert long.endswith("…")