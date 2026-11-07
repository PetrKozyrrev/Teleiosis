import json
from urllib.parse import parse_qsl, urlencode

import pytest

from app.telegram_auth import InitDataError, validate_init_data
from tests.helpers import USER, build_init_data

TOKEN = "123456:TEST-token-not-real"  # выдуманный, не настоящий токен бота
NOW = 1_800_000_000


def check(init_data, **kwargs):
    return validate_init_data(init_data, TOKEN, now=NOW, **kwargs)


def good(**kwargs):
    kwargs.setdefault("auth_date", NOW - 10)
    return build_init_data(TOKEN, **kwargs)


def test_valid_init_data():
    result = check(good())
    assert result.telegram_id == 42
    assert result.username == "ivan_1"
    assert result.auth_date == NOW - 10


def test_user_without_username():
    result = check(good(user={"id": 7, "first_name": "Аня"}))
    assert result.telegram_id == 7
    assert result.username is None


def test_invalid_username_ignored():
    result = check(good(user={"id": 7, "username": "bad name!"}))
    assert result.username is None


def test_signature_field_is_part_of_check_string():
    # Telegram может присылать поле signature; оно подписывается наравне с остальными
    assert check(good(extra={"signature": "abc"})).telegram_id == 42


# ---------- подпись ----------


def test_wrong_token_rejected():
    with pytest.raises(InitDataError, match="bad signature"):
        validate_init_data(good(), "999:OTHER-token", now=NOW)


def test_empty_token_rejected():
    with pytest.raises(InitDataError, match="not configured"):
        validate_init_data(good(), "", now=NOW)


def test_tampered_user_rejected():
    fields = dict(parse_qsl(good()))
    fields["user"] = json.dumps({**USER, "id": 43})
    with pytest.raises(InitDataError, match="bad signature"):
        check(urlencode(fields))


def test_extra_field_after_signing_rejected():
    with pytest.raises(InitDataError, match="bad signature"):
        check(good() + "&foo=bar")


def test_duplicate_field_rejected():
    with pytest.raises(InitDataError, match="duplicate"):
        check(good() + "&auth_date=1")


def test_missing_hash_rejected():
    pairs = [(k, v) for k, v in parse_qsl(good()) if k != "hash"]
    with pytest.raises(InitDataError, match="hash"):
        check(urlencode(pairs))


@pytest.mark.parametrize("bad_hash", ["", "xyz", "A" * 64, "a" * 63, "a" * 65])
def test_bad_hash_format_rejected(bad_hash):
    fields = dict(parse_qsl(good()))
    fields["hash"] = bad_hash
    with pytest.raises(InitDataError, match="hash"):
        check(urlencode(fields))


@pytest.mark.parametrize("raw", [None, "", "a=b", "hash=" + "a" * 64, "x" * 9000])
def test_garbage_rejected(raw):
    with pytest.raises(InitDataError):
        check(raw)


# ---------- свежесть ----------


def test_age_boundary():
    assert check(good(auth_date=NOW - 3600), max_age=3600)
    with pytest.raises(InitDataError, match="expired"):
        check(good(auth_date=NOW - 3601), max_age=3600)


def test_future_date_rejected_with_small_skew_allowed():
    assert check(good(auth_date=NOW + 30))
    with pytest.raises(InitDataError, match="future"):
        check(good(auth_date=NOW + 3600))


@pytest.mark.parametrize("raw", ["abc", "-5", "", "1.5", " 12", "9" * 20])
def test_bad_auth_date_rejected(raw):
    with pytest.raises(InitDataError, match="auth_date"):
        check(good(extra={"auth_date": raw}))


def test_missing_auth_date_rejected():
    with pytest.raises(InitDataError, match="auth_date"):
        check(good(drop=("auth_date",)))


# ---------- пользователь ----------


def test_missing_user_rejected():
    with pytest.raises(InitDataError, match="no user"):
        check(good(user=None))


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1]",
        "null",
        '{"first_name":"x"}',
        '{"id":"42"}',
        '{"id":true}',
        '{"id":1.5}',
        '{"id":0}',
        '{"id":-5}',
        '{"id":99999999999999999999}',
    ],
)
def test_bad_user_rejected(raw):
    with pytest.raises(InitDataError, match="bad user"):
        check(good(user=None, extra={"user": raw}))