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


def test_saved_outcome_has_title_and_buttons_data():
    api = StubApi(
        SaveResult("saved", content={"id": 9, "title": "Название", "status": "unseen"})
    )
    outcome = describe(api)
    assert outcome.text.startswith("✅")
    assert "Название" in outcome.text
    assert outcome.content_id == 9
    assert outcome.status == "unseen"


def test_duplicate_outcome_shows_existing_title_and_id():
    api = StubApi(
        SaveResult("duplicate", existing_id=3),
        existing={"title": "Старое", "status": "studied"},
    )
    outcome = describe(api)
    assert outcome.text.startswith("ℹ️")
    assert "Старое" in outcome.text
    assert outcome.content_id == 3
    assert outcome.status == "studied"


def test_duplicate_without_content_has_generic_message_but_keeps_id():
    outcome = describe(StubApi(SaveResult("duplicate", existing_id=3), existing=None))
    assert "уже есть" in outcome.text
    assert outcome.content_id == 3
    assert outcome.status is None


def test_invalid_outcome_has_no_buttons():
    outcome = describe(StubApi(SaveResult("invalid")), url="http://bad")
    assert outcome.text.startswith("⚠️")
    assert "http://bad" in outcome.text
    assert outcome.content_id is None


def test_title_and_note_are_passed_to_api():
    api = StubApi(SaveResult("saved", content={"id": 1, "title": "Заголовок"}))
    describe(api, "https://t.me/durov/1", title="Заголовок", note="Текст")
    assert api.calls == [("url", "https://t.me/durov/1", "Заголовок", "Текст")]


def test_note_saved_outcome():
    api = StubApi(
        SaveResult(
            "saved",
            content={"id": 4, "title": "Идея", "content_type": "note", "status": "unseen"},
        )
    )
    outcome = asyncio.run(describe_note(api, 1, None, "Идея про рассылку"))
    assert outcome.text.startswith("📝")
    assert "Идея" in outcome.text
    assert outcome.content_id == 4
    assert api.calls == [("note", "Идея про рассылку")]


def test_note_invalid_outcome():
    outcome = asyncio.run(describe_note(StubApi(SaveResult("invalid")), 1, None, "x"))
    assert outcome.text.startswith("⚠️")
    assert outcome.content_id is None


def test_shorten():
    assert shorten("коротко") == "коротко"
    long = shorten("a" * 200, 100)
    assert len(long) == 100
    assert long.endswith("…")