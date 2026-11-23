from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from app.models import Content, ContentSubmission, User
from app.schemas import ContentCreate
from app.stats import reading_progress
from tests.test_mobile_auth import DATA, bearer


def test_mobile_profile_and_reading_progress(client, session):
    signed_in = client.post("/mobile/auth/register", json={**DATA, "display_name": "  Александра  "})
    assert signed_in.status_code == 201
    identity = signed_in.json()
    headers = bearer(identity["token"])
    profile = client.get("/mobile/profile", headers=headers)
    assert profile.headers["cache-control"] == "no-store"
    assert profile.json()["display_name"] == "Александра"
    assert profile.json()["weekly_reading_goal"] == 5
    assert client.patch("/mobile/profile", headers=headers, json={"weekly_reading_goal": 0}).status_code == 422
    assert client.patch("/mobile/profile", headers=headers, json={"weekly_reading_goal": 2}).status_code == 200

    user = session.get(User, identity["user"]["id"])
    user.timezone = "Europe/Moscow"
    now = datetime(2026, 11, 22, 21, 30, tzinfo=timezone.utc)
    session.add_all([
        Content(user_id=user.id, title="Понедельник", note="1", status="studied", studied_at=now),
        Content(user_id=user.id, title="Воскресенье", note="2", status="studied", studied_at=now - timedelta(hours=1)),
    ])
    session.commit()
    week = reading_progress(session, user, "week", 0, now)
    month = reading_progress(session, user, "month", 0, now)
    assert week["weekly_goal"] == 2
    assert week["weekly_completed"] == week["completed"] == 1
    assert week["streak"] == 2
    assert [row["title"] for row in week["recent"]] == ["Понедельник"]
    assert month["completed"] == 2
    assert client.get("/mobile/reading-progress?period=month", headers=headers).status_code == 200


def test_collections_and_url_save_together_and_legacy_receipt_replays(client, session, monkeypatch):
    monkeypatch.setattr("app.routers.contents.fetch_metadata", lambda url: None)
    identity = client.post("/mobile/auth/register", json=DATA).json()
    headers = bearer(identity["token"])
    base = "/mobile/library"
    group_a = client.post(f"{base}/collections", headers=headers, json={"name": "Первое"}).json()["id"]
    group_b = client.post(f"{base}/collections", headers=headers, json={"name": "Второе"}).json()["id"]
    payload = {"url": "https://example.com/first", "collection_ids": [group_a]}
    submission = {**headers, "Idempotency-Key": str(uuid4())}
    created = client.post(f"{base}/submissions", headers=submission, json=payload)
    assert created.status_code == 201, created.text
    material = created.json()
    assert client.post("/contents/submissions", headers=submission, json=payload).json()["id"] == material["id"]
    content = f'/contents/{material["id"]}'
    organization = f"{base}{content}/organization"
    with_version = {**headers, "If-Match": f'"{material["version"]}"'}
    assert client.patch(f"{content}/versioned", headers=with_version,
                        json={"url": "https://example.com/changed", "collection_ids": [999999]}).status_code == 404
    assert client.get(content, headers=headers).json()["url"] == payload["url"]
    edited = client.patch(f"{content}/versioned", headers=with_version,
                          json={"url": "https://example.com/changed", "collection_ids": [group_b]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == material["version"] + 1
    assert client.get(organization, headers=headers).json()["collections"] == [{"id": group_b, "name": "Второе"}]
    assert client.patch(f"{content}/versioned", headers=with_version, json={"status": "studied"}).status_code == 412
    latest = {**headers, "If-Match": f'"{edited.json()["version"]}"'}
    assert client.patch(f"{content}/versioned", headers=latest, json={"url": "https://example.com/url-only"}).json()["version"] == material["version"] + 2

    legacy_payload = {"note": "Запись до обновления"}
    legacy = client.post("/contents", headers=headers, json=legacy_payload).json()
    legacy_key = uuid4()
    session.add(ContentSubmission(user_id=identity["user"]["id"], content_id=legacy["id"], key=legacy_key, duplicate=False,
                                  fingerprint=sha256(ContentCreate(**legacy_payload).model_dump_json().encode()).hexdigest()))
    session.commit()
    replay = client.post("/contents/submissions", headers={**headers, "Idempotency-Key": str(legacy_key)}, json=legacy_payload)
    assert replay.status_code == 201
    assert replay.json()["id"] == legacy["id"]
