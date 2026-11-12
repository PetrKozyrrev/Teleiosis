from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

import app.routers.reminders as reminders_module
from app.models import Reminder
from tests.helpers import ORIGIN, auth_headers as auth


def save(client, telegram_id=1, **body):
    response = client.post("/contents", json=body, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()


def future(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def put(client, content_id, when, telegram_id=1, **extra):
    body = {"scheduled_at": when, **extra}
    return client.put(f"/contents/{content_id}/reminder", json=body, headers=auth(telegram_id))


def get(client, content_id, telegram_id=1):
    return client.get(f"/contents/{content_id}/reminder", headers=auth(telegram_id))


def delete(client, content_id, telegram_id=1):
    return client.delete(f"/contents/{content_id}/reminder", headers=auth(telegram_id))


def count(session, **filters):
    query = select(func.count()).select_from(Reminder)
    for name, value in filters.items():
        query = query.where(getattr(Reminder, name) == value)
    return session.scalar(query)


def instant(text):
    return datetime.fromisoformat(text)


def test_requires_auth(client):
    item = save(client, note="x")
    url = f"/contents/{item['id']}/reminder"
    when = {"scheduled_at": future(days=1)}
    assert client.get(url).status_code == 401
    assert client.put(url, json=when).status_code == 401
    assert client.delete(url).status_code == 401


def test_no_reminder_by_default(client):
    item = save(client, note="x")
    response = get(client, item["id"])
    assert response.status_code == 200
    assert response.json() is None


def test_create_and_read(client):
    item = save(client, note="x")
    when = future(days=1)
    response = put(client, item["id"], when)
    assert response.status_code == 200
    body = response.json()
    assert body["content_id"] == item["id"]
    assert body["status"] == "pending"
    assert instant(body["scheduled_at"]) == instant(when)
    assert get(client, item["id"]).json()["id"] == body["id"]


def test_offset_is_converted_to_the_same_instant(client):
    item = save(client, note="x")
    plus_three = timezone(timedelta(hours=3))
    when = (datetime.now(plus_three) + timedelta(days=2)).isoformat()
    body = put(client, item["id"], when).json()
    assert instant(body["scheduled_at"]) == instant(when)


def test_put_again_moves_the_same_reminder(client, session):
    item = save(client, note="x")
    first = put(client, item["id"], future(days=1)).json()
    later = future(days=5)
    second = put(client, item["id"], later).json()
    assert second["id"] == first["id"]
    assert instant(second["scheduled_at"]) == instant(later)
    assert count(session) == 1


def test_cancel_keeps_history_and_allows_a_new_one(client, session):
    item = save(client, note="x")
    first = put(client, item["id"], future(days=1)).json()
    assert delete(client, item["id"]).status_code == 204
    assert get(client, item["id"]).json() is None
    assert count(session, status="cancelled") == 1

    second = put(client, item["id"], future(days=2)).json()
    assert second["id"] != first["id"]
    assert count(session, status="pending") == 1


def test_cancel_without_reminder_is_harmless(client):
    item = save(client, note="x")
    assert delete(client, item["id"]).status_code == 204
    assert delete(client, item["id"]).status_code == 204


@pytest.mark.parametrize(
    "when",
    [
        (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        (datetime.now(timezone.utc) + timedelta(days=400)).isoformat(),
        (datetime.now() + timedelta(days=1)).replace(tzinfo=None).isoformat(),
        "tomorrow",
        "",
        1893456000,
        None,
    ],
    ids=["past", "too-far", "no-timezone", "text", "empty", "number", "null"],
)
def test_invalid_times_rejected(client, session, when):
    item = save(client, note="x")
    assert put(client, item["id"], when).status_code == 422
    assert count(session) == 0


def test_year_ahead_is_allowed(client):
    item = save(client, note="x")
    assert put(client, item["id"], future(days=365)).status_code == 200


def test_missing_and_extra_fields_rejected(client):
    item = save(client, note="x")
    url = f"/contents/{item['id']}/reminder"
    assert client.put(url, json={}, headers=auth(1)).status_code == 422
    body = {"scheduled_at": future(days=1), "status": "sent"}
    assert client.put(url, json=body, headers=auth(1)).status_code == 422


def test_other_user_cannot_touch_reminders(client, session):
    item = save(client, 1, note="x")
    put(client, item["id"], future(days=1), telegram_id=1)
    assert get(client, item["id"], telegram_id=2).status_code == 404
    assert put(client, item["id"], future(days=1), telegram_id=2).status_code == 404
    assert delete(client, item["id"], telegram_id=2).status_code == 404
    assert get(client, item["id"], telegram_id=1).json() is not None
    assert count(session) == 1


def test_missing_and_huge_ids(client):
    assert put(client, 999999, future(days=1)).status_code == 404
    assert get(client, 999999).status_code == 404
    assert put(client, 10**20, future(days=1)).status_code == 422


def test_limit_of_pending_reminders(client, monkeypatch):
    monkeypatch.setattr(reminders_module, "MAX_PENDING_PER_USER", 2)
    first, second, third = (save(client, note=f"заметка {i}") for i in range(3))
    assert put(client, first["id"], future(days=1)).status_code == 200
    assert put(client, second["id"], future(days=1)).status_code == 200
    assert put(client, third["id"], future(days=1)).status_code == 409
    # перенос существующего лимитом не блокируется
    assert put(client, first["id"], future(days=3)).status_code == 200
    # отмена освобождает место
    assert delete(client, second["id"]).status_code == 204
    assert put(client, third["id"], future(days=1)).status_code == 200


def test_limit_counts_each_user_separately(client, monkeypatch):
    monkeypatch.setattr(reminders_module, "MAX_PENDING_PER_USER", 1)
    mine = save(client, 1, note="x")
    theirs = save(client, 2, note="y")
    assert put(client, mine["id"], future(days=1), telegram_id=1).status_code == 200
    assert put(client, theirs["id"], future(days=1), telegram_id=2).status_code == 200


def test_deleting_the_material_removes_its_reminder(client, session):
    item = save(client, note="x")
    put(client, item["id"], future(days=1))
    assert client.delete(f"/contents/{item['id']}", headers=auth(1)).status_code == 204
    assert count(session) == 0


def test_cookie_session_needs_origin(client):
    body = {"email": "ivan@example.com", "password": "correct horse battery", "consent": True}
    assert client.post("/auth/register", json=body, headers={"Origin": ORIGIN}).status_code == 201
    item = client.post("/contents", json={"note": "x"}, headers={"Origin": ORIGIN}).json()
    url = f"/contents/{item['id']}/reminder"
    payload = {"scheduled_at": future(days=1)}
    assert client.put(url, json=payload).status_code == 403
    assert client.put(url, json=payload, headers={"Origin": ORIGIN}).status_code == 200
    assert client.delete(url).status_code == 403
    assert client.delete(url, headers={"Origin": ORIGIN}).status_code == 204