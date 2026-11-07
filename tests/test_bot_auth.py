import pytest

from app.config import settings

KEY = "k" * 40


def bot(telegram_id=1, key=KEY, username=None):
    headers = {"X-Bot-Key": key, "X-Telegram-Id": str(telegram_id)}
    if username is not None:
        headers["X-Telegram-Username"] = username
    return headers


@pytest.fixture(autouse=True)
def bot_key(monkeypatch):
    monkeypatch.setattr(settings, "bot_api_key", KEY)


def test_bot_creates_user_with_username(client):
    response = client.get("/me", headers=bot(77, username="ivan_1"))
    assert response.status_code == 200
    assert response.json()["telegram_id"] == 77
    assert response.json()["username"] == "ivan_1"


def test_repeat_request_returns_same_user(client):
    first = client.get("/me", headers=bot(77)).json()
    second = client.get("/me", headers=bot(77)).json()
    assert first["id"] == second["id"]


def test_no_credentials_rejected(client):
    assert client.get("/me").status_code == 401


def test_wrong_key_rejected(client):
    assert client.get("/me", headers=bot(key="x" * 40)).status_code == 401


def test_missing_telegram_id_rejected(client):
    assert client.get("/me", headers={"X-Bot-Key": KEY}).status_code == 401


def test_wrong_key_does_not_fall_back_to_dev_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    headers = bot(key="x" * 40)
    headers["X-Dev-Telegram-Id"] = "5"
    assert client.get("/me", headers=headers).status_code == 401


def test_short_configured_key_disables_bot_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "bot_api_key", "short")
    assert client.get("/me", headers=bot(key="short")).status_code == 401


def test_empty_key_disables_bot_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "bot_api_key", "")
    assert client.get("/me", headers=bot(key="")).status_code == 401


def test_username_updated_and_cleared(client):
    client.get("/me", headers=bot(77, username="old_name"))
    updated = client.get("/me", headers=bot(77, username="new_name")).json()
    assert updated["username"] == "new_name"
    cleared = client.get("/me", headers=bot(77)).json()
    assert cleared["username"] is None


def test_invalid_username_ignored(client):
    response = client.get("/me", headers=bot(77, username="bad name!"))
    assert response.status_code == 200
    assert response.json()["username"] is None


def test_invalid_telegram_id_rejected(client):
    assert client.get("/me", headers=bot(telegram_id=0)).status_code == 422
    assert client.get("/me", headers=bot(telegram_id=10**20)).status_code == 422


def test_dev_auth_still_works(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    response = client.get("/me", headers={"X-Dev-Telegram-Id": "5"})
    assert response.status_code == 200
    assert response.json()["telegram_id"] == 5