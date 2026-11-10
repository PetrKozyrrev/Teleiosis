import pytest

from app.models import User
from tests.helpers import ORIGIN, auth_headers as auth


def patch(client, telegram_id=1, **body):
    return client.patch("/me/settings", json=body, headers=auth(telegram_id))


def me(client, telegram_id=1):
    return client.get("/me", headers=auth(telegram_id)).json()


def test_requires_auth(client):
    assert client.patch("/me/settings", json={"timezone": "UTC"}).status_code == 401


def test_me_has_reminder_fields_with_defaults(client):
    body = me(client)
    assert body["timezone"] == "UTC"
    assert body["reminders_enabled"] is True
    assert body["reminder_time"] == "09:00"
    assert body["email_verified_at"] is None


def test_update_all_fields(client):
    response = patch(
        client, timezone="Asia/Vladivostok", reminders_enabled=False, reminder_time="07:30"
    )
    assert response.status_code == 200
    expected = {"timezone": "Asia/Vladivostok", "reminders_enabled": False, "reminder_time": "07:30"}
    assert {key: response.json()[key] for key in expected} == expected
    assert {key: me(client)[key] for key in expected} == expected


def test_partial_update_keeps_other_fields(client):
    patch(client, timezone="Europe/Moscow", reminder_time="08:15")
    response = patch(client, reminders_enabled=False)
    body = response.json()
    assert body["reminders_enabled"] is False
    assert body["timezone"] == "Europe/Moscow"
    assert body["reminder_time"] == "08:15"


@pytest.mark.parametrize("value", ["00:00", "09:05", "23:59"])
def test_valid_times(client, value):
    assert patch(client, reminder_time=value).json()["reminder_time"] == value


@pytest.mark.parametrize(
    "value", ["9:00", "24:00", "12:60", "12:00:30", "12:00+03:00", "", "noon", 1800, None]
)
def test_invalid_times_rejected(client, value):
    assert patch(client, reminder_time=value).status_code == 422
    assert me(client)["reminder_time"] == "09:00"


@pytest.mark.parametrize(
    "value",
    ["", "Moscow", "Europe/Nowhere", "../etc/passwd", " Europe/Moscow", "europe/moscow", 5, None],
)
def test_invalid_timezones_rejected(client, value):
    assert patch(client, timezone=value).status_code == 422
    assert me(client)["timezone"] == "UTC"


@pytest.mark.parametrize("value", ["yes", "true", 1, 0, None])
def test_reminders_enabled_must_be_a_real_boolean(client, value):
    assert patch(client, reminders_enabled=value).status_code == 422
    assert me(client)["reminders_enabled"] is True


def test_empty_body_rejected(client):
    assert patch(client).status_code == 422


@pytest.mark.parametrize("field", ["email", "user_id", "password_hash", "email_verified_at"])
def test_unknown_fields_rejected(client, field):
    assert patch(client, **{field: "x", "reminders_enabled": False}).status_code == 422
    assert me(client)["reminders_enabled"] is True


def test_invalid_field_changes_nothing(client):
    assert patch(client, reminders_enabled=False, reminder_time="bad").status_code == 422
    assert me(client)["reminders_enabled"] is True


def test_settings_are_per_user(client):
    patch(client, 1, timezone="Asia/Tokyo")
    assert me(client, 2)["timezone"] == "UTC"


def test_cookie_session_needs_origin(client):
    body = {"email": "ivan@example.com", "password": "correct horse battery", "consent": True}
    assert client.post("/auth/register", json=body, headers={"Origin": ORIGIN}).status_code == 201
    change = {"reminders_enabled": False}
    assert client.patch("/me/settings", json=change).status_code == 403
    assert client.patch("/me/settings", json=change, headers={"Origin": ORIGIN}).status_code == 200


def test_last_digest_on_is_empty_by_default(session):
    user = User(email="a@example.com")
    session.add(user)
    session.flush()
    session.refresh(user)
    assert user.last_digest_on is None