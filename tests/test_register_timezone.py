import pytest

from tests.helpers import ORIGIN


def register(client, **extra):
    body = {"email": "ivan@example.com", "password": "correct horse battery", "consent": True}
    body.update(extra)
    return client.post("/auth/register", json=body, headers={"Origin": ORIGIN})


def test_browser_timezone_is_saved(client):
    response = register(client, timezone="Asia/Vladivostok")
    assert response.status_code == 201
    assert response.json()["timezone"] == "Asia/Vladivostok"


def test_without_timezone_utc_is_used(client):
    assert register(client).json()["timezone"] == "UTC"


@pytest.mark.parametrize("value", ["Europe/Nowhere", "", "x" * 100, "../etc/passwd"])
def test_unknown_timezone_falls_back_to_utc(client, value):
    response = register(client, timezone=value)
    assert response.status_code == 201
    assert response.json()["timezone"] == "UTC"


def test_timezone_of_wrong_type_rejected(client):
    assert register(client, timezone=5).status_code == 422