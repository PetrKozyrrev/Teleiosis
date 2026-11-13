from datetime import datetime, timedelta, timezone

import app.routers.users as users_module
from app.ratelimit import Rule
from tests.helpers import ORIGIN, auth_headers as auth


def save(client, telegram_id=1, **body):
    response = client.post("/contents", json=body, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()


def export(client, telegram_id=1):
    return client.get("/me/export", headers=auth(telegram_id))


def test_requires_auth(client):
    assert client.get("/me/export").status_code == 401


def test_headers(client):
    response = export(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert "teleiosis-export.json" in response.headers["content-disposition"]


def test_empty_account(client):
    body = export(client).json()
    assert body["version"] == 1
    assert body["user"]["telegram_id"] == 1
    assert body["categories"] == []
    assert body["contents"] == []
    assert body["reminders"] == []
    assert body["activity_days"] == []


def test_contains_all_own_data(client):
    category = client.post("/categories", json={"name": "Бизнес"}, headers=auth(1)).json()
    item = save(client, note="Идея про рассылку", category_id=category["id"])
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    response = client.put(
        f"/contents/{item['id']}/reminder", json={"scheduled_at": when}, headers=auth(1)
    )
    assert response.status_code == 200

    body = export(client).json()
    assert [c["name"] for c in body["categories"]] == ["Бизнес"]
    assert len(body["contents"]) == 1
    content = body["contents"][0]
    assert content["note"] == "Идея про рассылку"
    assert content["category_id"] == category["id"]
    assert content["status"] == "unseen"
    assert [r["status"] for r in body["reminders"]] == ["pending"]
    assert body["reminders"][0]["content_id"] == item["id"]
    assert len(body["activity_days"]) == 1


def test_only_own_data(client):
    save(client, 1, note="мой")
    save(client, 2, note="чужой")
    client.post("/categories", json={"name": "Чужая"}, headers=auth(2))

    body = export(client, 1).json()
    assert [c["note"] for c in body["contents"]] == ["мой"]
    assert body["categories"] == []
    assert "чужой" not in export(client, 1).text


def test_no_password_hash_or_secrets(client):
    register = {"email": "ivan@example.com", "password": "correct horse battery", "consent": True}
    assert client.post("/auth/register", json=register, headers={"Origin": ORIGIN}).status_code == 201

    response = client.get("/me/export")  # по cookie, GET без Origin разрешён
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ivan@example.com"
    assert "password" not in body["user"]
    assert "password_hash" not in response.text
    assert "argon2" not in response.text
    assert "token" not in response.text


def test_export_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(users_module, "EXPORT_USER", Rule("export_user", 2, timedelta(hours=1)))
    assert export(client).status_code == 200
    assert export(client).status_code == 200
    blocked = export(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_export_does_not_count_as_activity(client, session):
    from sqlalchemy import func, select

    from app.models import UserActivity

    export(client)
    assert session.scalar(select(func.count()).select_from(UserActivity)) == 0