import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.helpers import auth_headers as auth


def save(client, telegram_id=1, **body):
    response = client.post("/contents", json=body, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()


def open_it(client, content_id, telegram_id=1):
    return client.post(f"/contents/{content_id}/open", headers=auth(telegram_id))


def get(client, content_id, telegram_id=1):
    return client.get(f"/contents/{content_id}", headers=auth(telegram_id))


def test_new_material_has_no_openings(client):
    item = save(client, url="https://example.com/a")
    assert item["open_count"] == 0
    assert item["last_opened_at"] is None


def test_open_is_counted(client):
    item = save(client, url="https://example.com/a")
    assert open_it(client, item["id"]).status_code == 204
    body = get(client, item["id"]).json()
    assert body["open_count"] == 1
    assert body["last_opened_at"] is not None

    assert open_it(client, item["id"]).status_code == 204
    assert get(client, item["id"]).json()["open_count"] == 2
    listed = client.get("/contents", headers=auth(1)).json()["items"][0]
    assert listed["open_count"] == 2


def test_open_does_not_change_status_or_updated_at(client, session):
    item = save(client, url="https://example.com/a")
    session.execute(
        text("UPDATE contents SET updated_at = now() - interval '1 day' WHERE id = :id"),
        {"id": item["id"]},
    )
    session.expire_all()
    before = get(client, item["id"]).json()

    assert open_it(client, item["id"]).status_code == 204
    session.expire_all()
    after = get(client, item["id"]).json()
    assert after["updated_at"] == before["updated_at"]
    assert after["status"] == before["status"] == "unseen"


def test_open_requires_auth(client):
    item = save(client, url="https://example.com/a")
    assert client.post(f"/contents/{item['id']}/open").status_code == 401


def test_other_user_cannot_open_and_count_stays(client):
    item = save(client, 1, url="https://example.com/a")
    assert open_it(client, item["id"], telegram_id=2).status_code == 404
    assert get(client, item["id"], 1).json()["open_count"] == 0


def test_missing_and_huge_ids(client):
    assert open_it(client, 999999).status_code == 404
    assert open_it(client, 10**20).status_code == 422


def test_counters_cannot_be_patched(client):
    item = save(client, url="https://example.com/a")
    for body in ({"open_count": 5}, {"last_opened_at": "2026-01-01T00:00:00Z"}):
        response = client.patch(f"/contents/{item['id']}", json=body, headers=auth(1))
        assert response.status_code == 422


def test_open_count_cannot_be_negative(client, session):
    item = save(client, url="https://example.com/a")
    with pytest.raises(IntegrityError):
        session.execute(
            text("UPDATE contents SET open_count = -1 WHERE id = :id"), {"id": item["id"]}
        )