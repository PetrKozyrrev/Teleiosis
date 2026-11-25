import app.routers.contents as contents_module
from app.metadata import Metadata
from tests.helpers import auth_headers as auth


def save(client, user_key=1, **body):
    return client.post("/contents", json=body, headers=auth(user_key))


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
    response = save(client, note="Я" * 1001)
    assert response.status_code == 201
    assert response.json()["reading_minutes"] == 2
    assert calls == []


def test_list_includes_source_duration_and_reading_estimates(client, monkeypatch):
    stub(monkeypatch, Metadata(video_duration_seconds=753))
    video = save(client, url="https://youtu.be/dQw4w9WgXcQ").json()
    stub(monkeypatch, Metadata(text_character_count=2400))
    article = save(client, url="https://example.com/a").json()

    items = {item["id"]: item for item in client.get("/contents", headers=auth(1)).json()["items"]}
    assert items[video["id"]]["video_duration_seconds"] == 753
    assert items[video["id"]]["reading_minutes"] is None
    assert items[article["id"]]["reading_minutes"] == 3
    assert "text_character_count" not in items[article["id"]]


def test_duplicate_does_not_trigger_second_fetch(client, monkeypatch):
    calls = stub(monkeypatch, None)
    assert save(client, url="https://example.com/a").status_code == 201
    assert save(client, url="https://www.example.com/a?utm_source=x").status_code == 409
    assert len(calls) == 1


def test_invalid_category_does_not_trigger_fetch(client, monkeypatch):
    calls = stub(monkeypatch, None)
    assert save(client, url="https://example.com/a", category_id=999999).status_code == 404
    assert calls == []
