import threading
import time
from datetime import timedelta
from string import hexdigits
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text

import app.passwords as passwords
import app.routers.auth as auth_module
from app.models import RateLimitEvent, User
from app.passwords import hash_password
from app.ratelimit import (
    Rule,
    blocked_for,
    check_limits,
    clear,
    client_ip,
    make_key,
    record,
)
from tests.helpers import ORIGIN

EMAIL = "ivan@example.com"
PASSWORD = "correct horse battery"
WRONG = "wrong wrong wrong"
WITH_ORIGIN = {"Origin": ORIGIN}
RULE = Rule("test", 3, timedelta(minutes=10))


# ---------- адрес клиента и ключи ----------


def fake_request(host):
    return SimpleNamespace(client=SimpleNamespace(host=host) if host else None)


@pytest.mark.parametrize(
    "host, expected",
    [
        ("203.0.113.5", "203.0.113.5"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::"),
        ("2001:db8:1:2:ffff::1", "2001:db8:1:2::"),
        ("::ffff:203.0.113.5", "203.0.113.5"),
        ("testclient", "testclient"),
        (None, "unknown"),
    ],
)
def test_client_ip(host, expected):
    assert client_ip(fake_request(host)) == expected


def test_make_key_is_stable_sha256_without_ambiguity():
    key = make_key("a@example.com", "203.0.113.5")
    assert key == make_key("a@example.com", "203.0.113.5")
    assert len(key) == 64 and all(c in hexdigits for c in key)
    assert make_key("a", "bc") != make_key("ab", "c")


# ---------- счётчики ----------


def count_events(session, bucket=None):
    query = select(func.count()).select_from(RateLimitEvent)
    if bucket:
        query = query.where(RateLimitEvent.bucket == bucket)
    return session.scalar(query)


def test_blocked_only_after_limit_is_reached(session):
    key = make_key("a")
    assert blocked_for(session, RULE, key) is None
    record(session, RULE, key)
    record(session, RULE, key)
    assert blocked_for(session, RULE, key) is None
    record(session, RULE, key)
    wait = blocked_for(session, RULE, key)
    assert wait is not None and 1 <= wait <= 600


def test_other_keys_and_buckets_are_independent(session):
    key = make_key("a")
    for _ in range(3):
        record(session, RULE, key)
    assert blocked_for(session, RULE, make_key("b")) is None
    assert blocked_for(session, Rule("other", 3, timedelta(minutes=10)), key) is None


def test_events_outside_the_window_are_ignored(session):
    key = make_key("a")
    for _ in range(3):
        record(session, RULE, key)
    session.execute(text("UPDATE rate_limit_events SET created_at = now() - interval '11 minutes'"))
    assert blocked_for(session, RULE, key) is None


def test_retry_after_counts_from_the_oldest_event(session):
    key = make_key("a")
    for _ in range(3):
        record(session, RULE, key)
    session.execute(text("UPDATE rate_limit_events SET created_at = now() - interval '9 minutes'"))
    assert 45 <= blocked_for(session, RULE, key) <= 61


def test_clear_resets_counter(session):
    key = make_key("a")
    for _ in range(3):
        record(session, RULE, key)
    clear(session, RULE, key)
    assert blocked_for(session, RULE, key) is None


def test_old_records_are_removed_on_write(session):
    old_key, new_key = make_key("old"), make_key("new")
    record(session, RULE, old_key)
    session.execute(text("UPDATE rate_limit_events SET created_at = now() - interval '3 hours'"))
    record(session, RULE, new_key)
    assert session.scalars(select(RateLimitEvent.key_hash)).all() == [new_key]


def test_check_limits_reports_the_longest_wait(session):
    short = Rule("t1", 1, timedelta(minutes=10))
    long = Rule("t2", 1, timedelta(hours=1))
    key = make_key("a")
    record(session, short, key)
    record(session, long, key)
    with pytest.raises(HTTPException) as exc:
        check_limits(session, (short, key), (long, key))
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 600


# ---------- вход ----------


def make_user(session):
    user = User(email=EMAIL, password_hash=hash_password(PASSWORD))
    session.add(user)
    session.flush()
    return user


def post_login(client, email=EMAIL, password=PASSWORD):
    body = {"email": email, "password": password}
    return client.post("/auth/login", json=body, headers=WITH_ORIGIN)


def test_login_blocked_after_five_failures(client, session):
    make_user(session)
    for _ in range(5):
        assert post_login(client, password=WRONG).status_code == 401
    blocked = post_login(client, password=WRONG)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    # пока действует блокировка, не пускает и верный пароль
    assert post_login(client).status_code == 429


def test_blocked_attempts_are_not_recorded(client, session):
    make_user(session)
    for _ in range(5):
        post_login(client, password=WRONG)
    post_login(client, password=WRONG)
    post_login(client)
    assert count_events(session, "login_email_ip") == 5
    assert count_events(session, "login_ip") == 5


def test_unknown_email_is_limited_like_a_known_one(client, session):
    make_user(session)
    for email in (EMAIL, "nobody@example.com"):
        for _ in range(5):
            assert post_login(client, email=email, password=WRONG).status_code == 401
    known = post_login(client, email=EMAIL, password=WRONG)
    unknown = post_login(client, email="nobody@example.com", password=WRONG)
    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()


def test_success_resets_the_pair_counter(client, session):
    make_user(session)
    for _ in range(4):
        assert post_login(client, password=WRONG).status_code == 401
    assert post_login(client).status_code == 200
    assert count_events(session, "login_email_ip") == 0
    for _ in range(4):
        assert post_login(client, password=WRONG).status_code == 401


def test_ip_limit_covers_all_emails(client, session, monkeypatch):
    monkeypatch.setattr(auth_module, "LOGIN_IP", Rule("login_ip", 3, timedelta(minutes=15)))
    make_user(session)
    for i in range(3):
        assert post_login(client, email=f"user{i}@example.com", password=WRONG).status_code == 401
    assert post_login(client, email="another@example.com", password=WRONG).status_code == 429
    assert post_login(client).status_code == 429


def test_other_ip_is_not_affected(client, session, monkeypatch):
    current = {"ip": "203.0.113.1"}
    monkeypatch.setattr(auth_module, "client_ip", lambda request: current["ip"])
    make_user(session)
    for _ in range(5):
        post_login(client, password=WRONG)
    assert post_login(client).status_code == 429
    current["ip"] = "203.0.113.2"
    assert post_login(client).status_code == 200


def test_blocked_login_does_no_password_work(client, session, monkeypatch):
    calls = []
    monkeypatch.setattr(auth_module, "verify_password", lambda *a: calls.append("v") or False)
    monkeypatch.setattr(auth_module, "verify_dummy", lambda *a: calls.append("d"))
    make_user(session)
    for _ in range(5):
        assert post_login(client, password=WRONG).status_code == 401
    assert len(calls) == 5
    assert post_login(client, password=WRONG).status_code == 429
    assert len(calls) == 5


def test_journal_has_no_plain_email_or_ip(client, session):
    make_user(session)
    post_login(client, password=WRONG)
    keys = session.scalars(select(RateLimitEvent.key_hash)).all()
    assert keys
    assert all(len(k) == 64 and all(c in hexdigits for c in k) for k in keys)


# ---------- регистрация ----------


def post_register(client, email=EMAIL, password=PASSWORD, headers=WITH_ORIGIN):
    body = {"email": email, "password": password, "consent": True}
    return client.post("/auth/register", json=body, headers=headers)


def test_register_blocked_after_five_attempts(client):
    codes = [post_register(client).status_code for _ in range(5)]
    assert codes == [201, 409, 409, 409, 409]  # дубли тоже считаются
    blocked = post_register(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_invalid_register_requests_are_not_counted(client):
    for _ in range(6):
        assert post_register(client, password="short").status_code == 422
        assert post_register(client, headers={}).status_code == 403
    assert post_register(client).status_code == 201


def test_register_limit_is_per_ip(client, monkeypatch):
    current = {"ip": "203.0.113.1"}
    monkeypatch.setattr(auth_module, "client_ip", lambda request: current["ip"])
    for i in range(5):
        assert post_register(client, email=f"user{i}@example.com").status_code == 201
    assert post_register(client, email="extra@example.com").status_code == 429
    current["ip"] = "203.0.113.2"
    assert post_register(client, email="extra@example.com").status_code == 201


# ---------- ограничение одновременных проверок пароля ----------


def test_hashing_concurrency_is_capped(monkeypatch):
    state = {"running": 0, "peak": 0}
    lock = threading.Lock()

    def work():
        with lock:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        time.sleep(0.05)
        with lock:
            state["running"] -= 1

    class FakeHasher:
        def hash(self, password):
            work()
            return "hash"

        def verify(self, password_hash, password):
            work()
            return True

    monkeypatch.setattr(passwords, "_hasher", FakeHasher())
    threads = []
    for i in range(passwords.HASH_CONCURRENCY * 3):
        if i % 2:
            threads.append(threading.Thread(target=passwords.hash_password, args=("pw",)))
        else:
            threads.append(threading.Thread(target=passwords.verify_password, args=("pw", "h")))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert 1 < state["peak"] <= passwords.HASH_CONCURRENCY