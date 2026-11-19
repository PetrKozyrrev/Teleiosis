from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.config import settings
from app.models import PushDelivery, PushDevice, Reminder, User
from app.push import SendResult, plan_deliveries, process_push, send_rustore


@pytest.fixture
def push_enabled(monkeypatch):
    monkeypatch.setattr(settings, "push_enabled", True)


def account(client):
    password = "synthetic-push-password"
    created = client.post("/mobile/auth/register", json={
        "email": f"push-{uuid4().hex}@example.com", "password": password, "consent": True,
    })
    assert created.status_code == 201
    return {"Authorization": "Bearer " + created.json()["token"]}, created.json()["user"]["id"]


def device(client, headers, token="synthetic-device-token"):
    device_id = uuid4()
    response = client.put(f"/mobile/devices/{device_id}", headers=headers, json={"token": token, "enabled": True})
    assert response.status_code == 200
    assert "token" not in response.json()
    return device_id


def due(client, session, headers, device_id):
    now = datetime.now(timezone.utc)
    material = client.post("/contents", headers=headers, json={"note": "Private synthetic text"}).json()
    reminder = client.put(f"/contents/{material['id']}/reminder", headers=headers, json={
        "scheduled_at": (now + timedelta(hours=1)).isoformat(),
    })
    assert reminder.status_code == 200
    session.execute(update(PushDevice).where(PushDevice.id == device_id).values(enabled_at=now - timedelta(hours=2)))
    session.execute(update(Reminder).where(Reminder.id == reminder.json()["id"]).values(scheduled_at=now - timedelta(minutes=1)))
    # These cases exercise reminders only. Keep the daily digest outside its window.
    from datetime import time
    session.execute(update(User).values(reminder_time=time((now.hour + 12) % 24), timezone="UTC"))
    session.commit()
    return now, material, reminder.json()["id"]


def test_disabled_push_has_no_side_effect(client, session):
    headers, _ = account(client)
    assert client.put(f"/mobile/devices/{uuid4()}", headers=headers, json={"token": "synthetic-token-only", "enabled": True}).status_code == 503
    assert process_push(session, datetime.now(timezone.utc)) == 0
    assert session.scalars(select(PushDevice)).all() == []


def test_registration_rotation_and_logout_cascade(client, session, push_enabled):
    headers, _ = account(client)
    other, _ = account(client)
    device_id = device(client, headers)
    assert client.put(f"/mobile/devices/{device_id}", headers=other, json={"token": "synthetic-token-other", "enabled": True}).status_code == 409
    assert client.delete(f"/mobile/devices/{device_id}", headers=other).status_code == 204
    assert session.get(PushDevice, device_id) is not None
    response = client.put(f"/mobile/devices/{device_id}", headers=headers, json={"token": "synthetic-rotated-token", "enabled": True})
    assert response.status_code == 200
    assert session.get(PushDevice, device_id, populate_existing=True).token == "synthetic-rotated-token"
    assert client.post("/mobile/auth/logout", headers=headers, json={}).status_code == 204
    session.expire_all()
    assert session.get(PushDevice, device_id) is None


def test_device_registration_rejects_browser_transport(client, session, push_enabled):
    headers, _ = account(client)
    path = f"/mobile/devices/{uuid4()}"
    body = {"token": "synthetic-device-token", "enabled": True}
    assert client.put(path, headers={**headers, "Origin": "https://example.com"}, json=body).status_code == 403
    assert client.put(path, headers={**headers, "Cookie": "session=synthetic-cookie"}, json=body).status_code == 401
    assert not session.scalars(select(PushDevice)).all()


def test_one_delivery_per_device_and_event(client, session, push_enabled):
    headers, _ = account(client)
    device_id = device(client, headers)
    now, material, _ = due(client, session, headers, device_id)
    calls = []
    def send(token, delivery, current):
        calls.append(delivery.id)
        return SendResult("accepted")
    process_push(session, now, send)
    process_push(session, now + timedelta(seconds=1), send)
    rows = session.scalars(select(PushDelivery).where(PushDelivery.reminder_id.is_not(None))).all()
    assert len(rows) == 1 and rows[0].status == "accepted"
    assert calls.count(rows[0].id) == 1


@pytest.mark.parametrize("operation", ["cancel", "studied", "reschedule", "logout", "off"])
def test_retry_rechecks_owner_settings_and_material(client, session, push_enabled, operation):
    headers, _ = account(client)
    device_id = device(client, headers)
    now, material, _ = due(client, session, headers, device_id)
    process_push(session, now, lambda *_: SendResult("retry", 60))
    row = session.scalar(select(PushDelivery).where(PushDelivery.reminder_id.is_not(None)))
    assert row.status == "retry_wait"
    path = f"/contents/{material['id']}"
    if operation == "cancel":
        client.delete(path + "/reminder", headers=headers)
    elif operation == "reschedule":
        client.put(path + "/reminder", headers=headers, json={"scheduled_at": (now + timedelta(hours=2)).isoformat()})
    elif operation == "studied":
        client.patch(path, headers=headers, json={"status": "studied"})
    elif operation == "logout":
        client.post("/mobile/auth/logout", headers=headers, json={})
    else:
        client.put(f"/mobile/devices/{device_id}", headers=headers, json={"token": "synthetic-device-token", "enabled": False})
    calls = []
    process_push(session, now + timedelta(seconds=61), lambda *args: calls.append(args) or SendResult("accepted"))
    assert not calls


def test_invalid_token_disables_device(client, session, push_enabled):
    headers, _ = account(client)
    device_id = device(client, headers)
    now, _, _ = due(client, session, headers, device_id)
    process_push(session, now, lambda *_: SendResult("invalid"))
    registered = session.get(PushDevice, device_id, populate_existing=True)
    assert not registered.enabled and registered.token == ""


def test_expiry_stops_retry_after_worker_downtime(client, session, push_enabled):
    headers, _ = account(client)
    device_id = device(client, headers)
    now, _, _ = due(client, session, headers, device_id)
    process_push(session, now, lambda *_: SendResult("retry"))
    calls = []
    process_push(session, now + timedelta(hours=25), lambda *args: calls.append(args) or SendResult("accepted"))
    row = session.scalar(select(PushDelivery).where(PushDelivery.reminder_id.is_not(None)))
    assert row.status == "expired" and not calls


def test_completed_email_is_not_replanned_as_new_push(client, session, push_enabled):
    headers, _ = account(client)
    device_id = device(client, headers)
    now, material, reminder_id = due(client, session, headers, device_id)
    session.execute(update(Reminder).where(Reminder.id == reminder_id).values(status="sent"))
    session.commit()
    client.delete(f"/contents/{material['id']}/reminder", headers=headers)
    calls = []
    process_push(session, now, lambda *args: calls.append(args) or SendResult("accepted"))
    assert not calls


def test_recovery_of_abandoned_claim(client, session, push_enabled):
    headers, _ = account(client)
    device_id = device(client, headers)
    now, _, _ = due(client, session, headers, device_id)
    plan_deliveries(session, now)
    row = session.scalar(select(PushDelivery).where(PushDelivery.reminder_id.is_not(None)))
    row.status = "sending"
    row.next_attempt_at = now + timedelta(seconds=45)
    session.commit()
    calls = []
    send = lambda *args: calls.append(args) or SendResult("accepted")
    process_push(session, now + timedelta(seconds=44), send)
    assert not calls
    process_push(session, now + timedelta(seconds=46), send)
    assert len(calls) == 1


def test_two_devices_and_token_transfer(client, session, push_enabled):
    headers, _ = account(client)
    first = device(client, headers, "synthetic-device-first")
    second = device(client, headers, "synthetic-device-second")
    now, _, _ = due(client, session, headers, first)
    session.execute(update(PushDevice).where(PushDevice.id == second).values(enabled_at=now - timedelta(hours=2)))
    session.commit()
    process_push(session, now, lambda *_: SendResult("retry"))
    assert len(session.scalars(select(PushDelivery).where(PushDelivery.reminder_id.is_not(None))).all()) == 2
    other, _ = account(client)
    replacement = device(client, other, "synthetic-device-first")
    session.expire_all()
    assert session.get(PushDevice, first) is None
    assert session.get(PushDevice, replacement) is not None
    calls = []
    process_push(session, now + timedelta(seconds=60), lambda token, *_: calls.append(token) or SendResult("accepted"))
    assert calls == ["synthetic-device-second"]


def test_daily_digest_deduplicates_and_respects_enable_time(client, session, push_enabled):
    from datetime import time
    headers, user_id = account(client)
    device_id = device(client, headers)
    now, _, reminder_id = due(client, session, headers, device_id)
    now = now.replace(hour=12, minute=30)
    session.execute(update(Reminder).where(Reminder.id == reminder_id).values(status="cancelled"))
    session.execute(update(User).where(User.id == user_id).values(timezone="UTC", reminder_time=time(12)))
    session.execute(update(PushDevice).where(PushDevice.id == device_id).values(enabled_at=now - timedelta(hours=1)))
    session.commit()
    calls = []
    send = lambda *args: calls.append(args) or SendResult("accepted")
    process_push(session, now, send)
    process_push(session, now + timedelta(minutes=1), send)
    assert len(calls) == 1
    row = session.scalar(select(PushDelivery))
    assert row.event_key.startswith("digest/") and row.status == "accepted"


@pytest.mark.parametrize("status,body,outcome", [
    (404, {"error": {"status": "NOT_FOUND"}}, "invalid"),
    (404, {}, "failed"), (401, {}, "failed"), (403, {}, "failed"),
    (429, {}, "retry"), (503, {}, "retry"), (302, {}, "failed"),
    (400, {"error": []}, "failed"),
    (400, {"error": {"status": "INVALID_ARGUMENT", "message": "The registration token is not a valid FCM registration token"}}, "invalid"),
])
def test_provider_error_classification(monkeypatch, status, body, outcome):
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *_, **__: httpx.Response(status, json=body))
    now = datetime.now(timezone.utc)
    row = PushDelivery(id=uuid4(), content_id=9, expires_at=now + timedelta(minutes=5))
    assert send_rustore("synthetic-device-token", row, now).outcome == outcome


def test_provider_uses_minimal_payload_and_explicit_ttl(monkeypatch):
    from pydantic import SecretStr
    import httpx
    monkeypatch.setattr(settings, "rustore_project_id", "synthetic-project")
    monkeypatch.setattr(settings, "rustore_service_token", SecretStr("synthetic-service-token"))
    calls = []
    def post(url, **options):
        calls.append((url, options))
        return httpx.Response(200)
    monkeypatch.setattr(httpx, "post", post)
    now = datetime.now(timezone.utc)
    row = PushDelivery(id=uuid4(), content_id=9, expires_at=now + timedelta(minutes=5))
    assert send_rustore("synthetic-device-token", row, now).outcome == "accepted"
    message = calls[0][1]["json"]["message"]
    assert message["android"]["ttl"] == "300s"
    assert set(message["data"]) == {"content_id", "delivery_id"}
    assert "Private" not in str(message)
    assert calls[0][1]["follow_redirects"] is False
