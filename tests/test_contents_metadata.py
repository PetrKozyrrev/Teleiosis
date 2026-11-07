import app.routers.contents as contents_module
from app.metadata import Metadata
from tests.helpers import auth_headers as auth


def save(client, telegram_id=1, **body):
    return client.post("/contents", json=body, headers=auth(telegram_id))


def stub(monkeypatch, result):
    calls = []

    def fake(url):
        calls.append(url)
        return result

    monkeypatch.setattr(contents_module, "fetch_metadata", fake)
    return calls


def test_metadata_fills_fields(client, monkeypatch):
    stub(monkeypatch, Metadata("Настоящее название", "Описание", "https://example.com/i.png"))
    body = save(client, url="https://example.com/a").json()
    assert body["title"] == "Настоящее название"
    assert body["description"] == "Описание"
    assert body["image_url"] == "https://example.com/i.png"


def test_user_title_wins(client, monkeypatch):
    stub(monkeypatch, Metadata("Загруженное", "Описание", None))
    body = save(client, url="https://example.com/a", title="Моё").json()
    assert body["title"] == "Моё"
    assert body["description"] == "Описание"


def test_fallback_title_when_nothing_fetched(client, monkeypatch):
    stub(monkeypatch, None)
    body = save(client, url="https://example.com/a").json()
    assert body["title"] == "example.com/a"
    assert body["description"] is None
    assert body["image_url"] is None


def test_fallback_title_when_metadata_has_no_title(client, monkeypatch):
    stub(monkeypatch, Metadata(None, "Только описание", None))
    body = save(client, url="https://example.com/a").json()
    assert body["title"] == "example.com/a"
    assert body["description"] == "Только описание"


def test_note_does_not_trigger_fetch(client, monkeypatch):
    calls = stub(monkeypatch, Metadata("X", None, None))
    assert save(client, note="просто заметка").status_code == 201
    assert calls == []


def test_duplicate_does_not_trigger_second_fetch(client, monkeypatch):
    calls = stub(monkeypatch, None)
    assert save(client, url="https://example.com/a").status_code == 201
    assert save(client, url="https://www.example.com/a?utm_source=x").status_code == 409
    assert len(calls) == 1


def test_invalid_category_does_not_trigger_fetch(client, monkeypatch):
    calls = stub(monkeypatch, None)
    assert save(client, url="https://example.com/a", category_id=999999).status_code == 404
    assert calls == []