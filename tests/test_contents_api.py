def auth(telegram_id):
    return {"X-Dev-Telegram-Id": str(telegram_id)}


def save(client, telegram_id=1, **body):
    return client.post("/contents", json=body, headers=auth(telegram_id))


def test_requires_auth(client):
    assert client.post("/contents", json={"url": "https://a.com"}).status_code == 401


def test_save_youtube_link(client):
    response = save(client, url="https://youtu.be/dQw4w9WgXcQ?si=abc")
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "youtube"
    assert body["content_type"] == "video"
    assert body["status"] == "unseen"
    assert body["url"] == "https://youtu.be/dQw4w9WgXcQ?si=abc"
    assert body["title"] == "youtube.com/watch?v=dQw4w9WgXcQ"


def test_custom_title_is_kept(client):
    body = save(client, url="https://example.com/a", title="  Мой заголовок  ").json()
    assert body["title"] == "Мой заголовок"


def test_save_note_without_url(client):
    response = save(client, note="Идея: проверить гипотезу\nвторая строка")
    assert response.status_code == 201
    body = response.json()
    assert body["content_type"] == "note"
    assert body["source"] == "other"
    assert body["url"] is None
    assert body["title"] == "Идея: проверить гипотезу"


def test_empty_request_rejected(client):
    assert save(client).status_code == 422
    assert save(client, url="  ", note=" ").status_code == 422


def test_invalid_url_rejected(client):
    assert save(client, url="ftp://example.com/x").status_code == 422
    assert save(client, url="not a url").status_code == 422


def test_duplicate_returns_409_with_existing_id(client):
    first = save(client, url="https://youtu.be/dQw4w9WgXcQ")
    second = save(client, url="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30")
    assert second.status_code == 409
    assert second.json()["detail"]["existing_id"] == first.json()["id"]


def test_same_link_for_different_users_allowed(client):
    assert save(client, 1, url="https://example.com/a").status_code == 201
    assert save(client, 2, url="https://example.com/a").status_code == 201


def test_two_notes_allowed(client):
    assert save(client, note="первая").status_code == 201
    assert save(client, note="вторая").status_code == 201


def test_category_assignment(client):
    category = client.post(
        "/categories", json={"name": "Бизнес"}, headers=auth(1)
    ).json()
    body = save(client, url="https://example.com/a", category_id=category["id"]).json()
    assert body["category_id"] == category["id"]


def test_foreign_or_missing_category_rejected(client):
    foreign = client.post(
        "/categories", json={"name": "Чужая"}, headers=auth(1)
    ).json()
    response = save(client, 2, url="https://example.com/a", category_id=foreign["id"])
    assert response.status_code == 404
    assert save(client, 1, url="https://example.com/b", category_id=999999).status_code == 404


def test_get_own_content_only(client):
    content_id = save(client, 1, url="https://example.com/a").json()["id"]
    assert client.get(f"/contents/{content_id}", headers=auth(1)).status_code == 200
    assert client.get(f"/contents/{content_id}", headers=auth(2)).status_code == 404