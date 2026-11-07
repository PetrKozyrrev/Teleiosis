import pytest
from sqlalchemy import text

from app.config import settings
from tests.helpers import USER, build_init_data

TOKEN = "123456:TEST-token-not-real"  # выдуманный токен бота
BOT_KEY = "k" * 40


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", TOKEN)
    monkeypatch.setattr(settings, "bot_api_key", BOT_KEY)


def login(client, user=USER):
    response = client.post(
        "/auth/telegram",
        json={"init_data": build_init_data(TOKEN, user=user)},
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_token_gives_access_to_own_user(client):
    response = client.get("/me", headers=bearer(login(client)))
    assert response.status_code == 200
    assert response.json()["telegram_id"] == 42


def test_scheme_is_case_insensitive(client):
    token = login(client)
    response = client.get("/me", headers={"Authorization": f"bearer {token}"})
    assert response.status_code == 200


def test_full_flow_save_and_list(client):
    headers = bearer(login(client))
    saved = client.post("/contents", json={"note": "через Mini App"}, headers=headers)
    assert saved.status_code == 201
    listing = client.get("/contents", headers=headers)
    assert listing.json()["total"] == 1


def test_data_is_isolated_between_tokens(client):
    first = bearer(login(client))
    second = bearer(login(client, user={"id": 43, "first_name": "Анна"}))
    item = client.post("/contents", json={"note": "секрет"}, headers=first).json()

    assert client.get("/contents", headers=second).json()["total"] == 0
    assert client.get(f"/contents/{item['id']}", headers=second).status_code == 404
    assert client.delete(f"/contents/{item['id']}", headers=second).status_code == 404
    assert client.get(f"/contents/{item['id']}", headers=first).status_code == 200


def test_unknown_token_rejected(client):
    login(client)
    assert client.get("/me", headers=bearer("A" * 43)).status_code == 401


@pytest.mark.parametrize(
    "value",
    [
        "Bearer",
        "Bearer ",
        "Basic abcdefghijklmnopqrstuvwxyz",
        "Token abcdefghijklmnopqrstuvwxyz",
        "abcdefghijklmnopqrstuvwxyz",
        "Bearer short",
        "Bearer bad chars!!bad chars!!bad",
        "Bearer " + "a" * 200,
    ],
)
def test_malformed_authorization_rejected(client, value):
    assert client.get("/me", headers={"Authorization": value}).status_code == 401


def test_too_long_header_rejected(client):
    response = client.get("/me", headers={"Authorization": "Bearer " + "a" * 600})
    assert response.status_code == 422


def test_expired_session_rejected(client, session):
    token = login(client)
    assert client.get("/me", headers=bearer(token)).status_code == 200
    session.execute(
        text(
            "UPDATE auth_sessions SET created_at = now() - interval '3 days', "
            "expires_at = now() - interval '1 day'"
        )
    )
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_deleted_session_rejected(client, session):
    token = login(client)
    session.execute(text("DELETE FROM auth_sessions"))
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_deleted_user_loses_access(client, session):
    token = login(client)
    session.execute(text("DELETE FROM users"))
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_bearer_with_bot_key_rejected(client):
    token = login(client)
    headers = {**bearer(token), "X-Bot-Key": BOT_KEY, "X-Telegram-Id": "42"}
    assert client.get("/me", headers=headers).status_code == 401


def test_token_is_not_a_bot_credential(client):
    token = login(client)
    # токен в заголовке бота не принимается
    headers = {"X-Bot-Key": token, "X-Telegram-Id": "42"}
    assert client.get("/me", headers=headers).status_code == 401


def test_dev_header_cannot_override_valid_token(client):
    token = login(client)
    headers = {**bearer(token), "X-Dev-Telegram-Id": "99"}
    response = client.get("/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["telegram_id"] == 42  # заголовок проигнорирован


def test_dev_header_cannot_rescue_bad_token(client):
    headers = {**bearer("A" * 43), "X-Dev-Telegram-Id": "5"}
    assert client.get("/me", headers=headers).status_code == 401