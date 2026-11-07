from sqlalchemy import select, text

from app.models import Reminder
from tests.helpers import auth_headers as auth


def save(client, telegram_id=1, **body):
    response = client.post("/contents", json=body, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()


def patch(client, content_id, telegram_id=1, **body):
    return client.patch(f"/contents/{content_id}", json=body, headers=auth(telegram_id))


def get(client, content_id, telegram_id=1):
    return client.get(f"/contents/{content_id}", headers=auth(telegram_id))


def test_requires_auth(client):
    item = save(client, url="https://example.com/a")
    assert client.patch(f"/contents/{item['id']}", json={"title": "X"}).status_code == 401
    assert client.delete(f"/contents/{item['id']}").status_code == 401


def test_update_title(client):
    item = save(client, url="https://example.com/a")
    response = patch(client, item["id"], title="  Новое название  ")
    assert response.status_code == 200
    assert response.json()["title"] == "Новое название"
    assert get(client, item["id"]).json()["title"] == "Новое название"


def test_invalid_title_rejected(client):
    item = save(client, url="https://example.com/a")
    for body in ({"title": ""}, {"title": "   "}, {"title": None}, {"title": "x" * 301}):
        assert patch(client, item["id"], **body).status_code == 422, body


def test_empty_body_rejected(client):
    item = save(client, url="https://example.com/a")
    assert patch(client, item["id"]).status_code == 422


def test_unknown_fields_rejected(client):
    item = save(client, url="https://example.com/a")
    assert patch(client, item["id"], url="https://other.com").status_code == 422
    assert patch(client, item["id"], title="X", user_id=5).status_code == 422
    assert patch(client, item["id"], url_normalized="x").status_code == 422


def test_studied_at_set_and_cleared(client):
    item = save(client, url="https://example.com/a")
    assert item["studied_at"] is None

    done = patch(client, item["id"], status="studied").json()
    assert done["status"] == "studied"
    assert done["studied_at"] is not None

    back = patch(client, item["id"], status="planned").json()
    assert back["status"] == "planned"
    assert back["studied_at"] is None


def test_repeated_studied_keeps_timestamp(client):
    item = save(client, url="https://example.com/a")
    first = patch(client, item["id"], status="studied").json()["studied_at"]
    second = patch(client, item["id"], status="studied").json()["studied_at"]
    assert first == second


def test_invalid_status_rejected(client):
    item = save(client, url="https://example.com/a")
    assert patch(client, item["id"], status="done").status_code == 422
    assert patch(client, item["id"], status=None).status_code == 422


def test_any_status_transition_allowed(client):
    item = save(client, url="https://example.com/a")
    for new_status in ("irrelevant", "planned", "studied", "unseen", "studied"):
        response = patch(client, item["id"], status=new_status)
        assert response.status_code == 200
        assert response.json()["status"] == new_status


def test_set_and_clear_category(client):
    category = client.post("/categories", json={"name": "Бизнес"}, headers=auth(1)).json()
    item = save(client, url="https://example.com/a")

    assigned = patch(client, item["id"], category_id=category["id"])
    assert assigned.json()["category_id"] == category["id"]

    cleared = patch(client, item["id"], category_id=None)
    assert cleared.status_code == 200
    assert cleared.json()["category_id"] is None


def test_foreign_or_missing_category_rejected(client):
    foreign = client.post("/categories", json={"name": "Чужая"}, headers=auth(1)).json()
    item = save(client, 2, url="https://example.com/a")

    assert patch(client, item["id"], 2, category_id=foreign["id"]).status_code == 404
    assert patch(client, item["id"], 2, category_id=999999).status_code == 404
    assert get(client, item["id"], 2).json()["category_id"] is None


def test_edit_and_clear_note(client):
    item = save(client, url="https://example.com/a")
    assert patch(client, item["id"], note="Мысль").json()["note"] == "Мысль"
    assert patch(client, item["id"], note=None).json()["note"] is None
    patch(client, item["id"], note="Снова")
    assert patch(client, item["id"], note="   ").json()["note"] is None


def test_note_only_material_keeps_note(client):
    item = save(client, note="только заметка")
    assert patch(client, item["id"], note=None).status_code == 422
    assert patch(client, item["id"], note="").status_code == 422
    assert get(client, item["id"]).json()["note"] == "только заметка"

    assert patch(client, item["id"], note="обновлённая").status_code == 200


def test_other_user_cannot_update_or_delete(client):
    item = save(client, 1, url="https://example.com/a", title="Мой")
    assert patch(client, item["id"], 2, title="Взлом").status_code == 404
    assert client.delete(f"/contents/{item['id']}", headers=auth(2)).status_code == 404

    mine = get(client, item["id"], 1)
    assert mine.status_code == 200
    assert mine.json()["title"] == "Мой"


def test_delete(client):
    item = save(client, url="https://example.com/a")
    assert client.delete(f"/contents/{item['id']}", headers=auth(1)).status_code == 204
    assert get(client, item["id"]).status_code == 404
    assert client.delete(f"/contents/{item['id']}", headers=auth(1)).status_code == 404


def test_delete_removes_reminders(client, session):
    item = save(client, url="https://example.com/a")
    user_id = client.get("/me", headers=auth(1)).json()["id"]
    session.add(
        Reminder(user_id=user_id, content_id=item["id"], scheduled_at=text("now()"))
    )
    session.flush()
    assert session.execute(select(Reminder)).first() is not None

    assert client.delete(f"/contents/{item['id']}", headers=auth(1)).status_code == 204
    assert session.execute(select(Reminder)).first() is None


def test_delete_keeps_other_items(client):
    first = save(client, url="https://example.com/a", title="A")
    save(client, url="https://example.com/b", title="B")
    client.delete(f"/contents/{first['id']}", headers=auth(1))

    items = client.get("/contents", headers=auth(1)).json()["items"]
    assert [i["title"] for i in items] == ["B"]


def test_huge_id_rejected(client):
    big = 10**20
    assert get(client, big).status_code == 422
    assert patch(client, big, title="X").status_code == 422
    assert client.delete(f"/contents/{big}", headers=auth(1)).status_code == 422