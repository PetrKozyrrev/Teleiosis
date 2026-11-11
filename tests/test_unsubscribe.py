import pytest
from sqlalchemy import select

from app.config import settings
from app.models import User
from app.schemas import MAX_BIGINT
from app.unsubscribe import (
    SecretKeyMissing,
    make_token,
    one_click_url,
    page_link,
    unsubscribe_headers,
    verify_token,
)
from tests.helpers import ORIGIN

WITH_ORIGIN = {"Origin": ORIGIN}
ONE_CLICK = "/auth/unsubscribe/one-click"


def make_user(session, email="a@example.com"):
    user = User(email=email)
    session.add(user)
    session.flush()
    session.refresh(user)
    assert user.reminders_enabled is True
    return user


def enabled(session, user):
    session.refresh(user)
    return user.reminders_enabled


def from_page(client, token, headers=WITH_ORIGIN):
    return client.post("/auth/unsubscribe", json={"token": token}, headers=headers)


def one_click(client, token):
    # Как почтовый сервис: форма без Origin и без cookie
    return client.post(f"{ONE_CLICK}?token={token}", data={"List-Unsubscribe": "One-Click"})


# ---------- токен ----------


def test_token_roundtrip():
    assert verify_token(make_token(7)) == 7


def test_token_of_another_user_cannot_be_forged():
    _, _, mac_of_seven = make_token(7).partition(".")
    assert verify_token(f"8.{mac_of_seven}") is None


def test_changed_signature_rejected():
    user_id, _, mac = make_token(7).partition(".")
    flipped = ("0" if mac[0] != "0" else "1") + mac[1:]
    assert verify_token(f"{user_id}.{flipped}") is None


@pytest.mark.parametrize(
    "token",
    [
        "", "abc", "7", "7.", ".abc", "0." + "a" * 64, "7." + "g" * 64,
        "7." + "A" * 64, "7." + "a" * 63, "7." + "a" * 65, f"{MAX_BIGINT + 1}." + "a" * 64,
        "-7." + "a" * 64, None, 5,
    ],
)
def test_malformed_tokens_rejected(token):
    assert verify_token(token) is None


def test_other_secret_invalidates_old_tokens(monkeypatch):
    token = make_token(7)
    monkeypatch.setattr(settings, "secret_key", "another-secret-" + "y" * 32)
    assert verify_token(token) is None


@pytest.mark.parametrize("key", ["", "short", "k" * 31])
def test_missing_or_short_key_is_an_error(monkeypatch, key):
    monkeypatch.setattr(settings, "secret_key", key)
    with pytest.raises(SecretKeyMissing):
        make_token(7)
    with pytest.raises(SecretKeyMissing):
        verify_token("7." + "a" * 64)
    assert verify_token("garbage") is None  # неверный формат отвергается без ключа


def test_links_and_headers():
    assert page_link(7).startswith(f"{ORIGIN}/app/unsubscribe.html#token=7.")
    assert one_click_url(7).startswith(f"{ORIGIN}{ONE_CLICK}?token=7.")
    headers = unsubscribe_headers(7)
    assert headers["List-Unsubscribe"] == f"<{one_click_url(7)}>"
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


# ---------- страница отписки ----------


def test_page_endpoint_disables_reminders(client, session):
    user = make_user(session)
    response = from_page(client, make_token(user.id))
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert enabled(session, user) is False


def test_page_endpoint_needs_origin(client, session):
    user = make_user(session)
    token = make_token(user.id)
    assert from_page(client, token, headers={}).status_code == 403
    assert from_page(client, token, headers={"Origin": "http://evil.example"}).status_code == 403
    assert enabled(session, user) is True


def test_repeat_is_harmless(client, session):
    user = make_user(session)
    token = make_token(user.id)
    assert from_page(client, token).status_code == 204
    assert from_page(client, token).status_code == 204
    assert enabled(session, user) is False


def test_only_the_token_owner_is_affected(client, session):
    first = make_user(session, "a@example.com")
    second = make_user(session, "b@example.com")
    assert from_page(client, make_token(first.id)).status_code == 204
    assert enabled(session, first) is False
    assert enabled(session, second) is True


def test_invalid_token_changes_nothing(client, session):
    user = make_user(session)
    _, _, mac = make_token(user.id).partition(".")
    forged = f"{user.id + 1}.{mac}"
    for token in ("garbage", forged):
        response = from_page(client, token)
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid token"}
    assert enabled(session, user) is True


def test_valid_token_of_a_deleted_user_is_not_an_error(client):
    assert from_page(client, make_token(999999)).status_code == 204


def test_page_endpoint_rejects_extra_fields_and_empty_token(client):
    body = {"token": make_token(1), "email": "a@example.com"}
    assert client.post("/auth/unsubscribe", json=body, headers=WITH_ORIGIN).status_code == 422
    assert from_page(client, "").status_code == 422


def test_no_login_is_needed(client, session):
    user = make_user(session)
    assert client.cookies.get("session") is None
    assert from_page(client, make_token(user.id)).status_code == 204


def test_unavailable_without_secret_key(client, monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "")
    assert from_page(client, "1." + "a" * 64).status_code == 503
    assert client.post(f"{ONE_CLICK}?token=1.{'a' * 64}").status_code == 503


# ---------- one-click (RFC 8058) ----------


def test_one_click_post_without_origin_disables_reminders(client, session):
    user = make_user(session)
    response = one_click(client, make_token(user.id))
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert enabled(session, user) is False


def test_one_click_get_does_nothing(client, session):
    user = make_user(session)
    response = client.get(f"{ONE_CLICK}?token={make_token(user.id)}")
    assert response.status_code == 405
    assert enabled(session, user) is True


def test_one_click_invalid_or_missing_token(client, session):
    user = make_user(session)
    assert one_click(client, "garbage").status_code == 400
    assert client.post(ONE_CLICK).status_code == 422
    assert client.post(f"{ONE_CLICK}?token={'a' * 200}").status_code == 422
    assert enabled(session, user) is True


def test_unsubscribed_user_gets_no_digest_by_flag(client, session):
    # Воркер (7.7) отбирает пользователей по этому полю
    user = make_user(session)
    assert one_click(client, make_token(user.id)).status_code == 204
    selected = session.scalars(select(User.id).where(User.reminders_enabled.is_(True))).all()
    assert user.id not in selected