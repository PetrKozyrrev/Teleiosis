from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import text

from app.config import settings
from app.digest import (
    CATCHUP_MINUTES,
    DIGEST_SIZE,
    build_digest_email,
    claim_digest,
    clean_title,
    is_due,
    pick_materials,
    process_due_users,
)
from app.models import Content, User
from app.unsubscribe import SecretKeyMissing
from tests.helpers import ORIGIN

# Москва 09:30, Владивосток 16:30
NOW = datetime(2026, 11, 11, 6, 30, tzinfo=timezone.utc)
AT = time(9, 0)


class Outbox:
    """Вместо send_email: запоминает письма."""

    def __init__(self, result=True, raise_for=()):
        self.calls = []
        self.result = result
        self.raise_for = set(raise_for)

    def __call__(self, to, subject, body, headers=None):
        if to in self.raise_for:
            raise RuntimeError("smtp exploded")
        self.calls.append({"to": to, "subject": subject, "body": body, "headers": headers or {}})
        return self.result

    @property
    def recipients(self):
        return [call["to"] for call in self.calls]


def make_user(session, email="a@example.com", tz="Europe/Moscow", at=AT,
              verified=True, enabled=True, last=None):
    user = User(
        email=email,
        timezone=tz,
        reminder_time=at,
        reminders_enabled=enabled,
        email_verified_at=NOW if verified else None,
        last_digest_on=last,
    )
    session.add(user)
    session.flush()
    return user


def add_content(session, user, title="Материал", status="unseen", created=None):
    row = Content(user_id=user.id, title=title, note="текст", status=status)
    session.add(row)
    session.flush()
    if created is not None:
        session.execute(
            text("UPDATE contents SET created_at = :ts WHERE id = :id"),
            {"ts": created, "id": row.id},
        )
    return row


def run(session, outbox, now=NOW, **kwargs):
    return process_due_users(session, now, send=outbox, **kwargs)


def day(number):
    return datetime(2026, 11, number, 12, 0, tzinfo=timezone.utc)


def local(hour, minute, number=11):
    return datetime(2026, 11, number, hour, minute)


# ---------- когда пора ----------


@pytest.mark.parametrize(
    "now, expected",
    [
        (local(8, 59), False),
        (local(9, 0), True),
        (local(9, 30), True),
        (local(11, 59), True),
        (local(12, 0), False),
        (local(18, 0), False),
    ],
)
def test_is_due_window(now, expected):
    assert CATCHUP_MINUTES == 180
    assert is_due(now, AT, None) is expected


def test_is_due_respects_minutes():
    assert is_due(local(9, 4), time(9, 5), None) is False
    assert is_due(local(9, 5), time(9, 5), None) is True


def test_is_due_only_once_per_local_day():
    assert is_due(local(9, 30), AT, date(2026, 11, 11)) is False
    assert is_due(local(9, 30), AT, date(2026, 11, 10)) is True
    assert is_due(local(9, 30), AT, date(2026, 11, 12)) is False  # пояс «уехал» назад


def test_window_ends_with_the_local_day():
    late = time(23, 30)
    assert is_due(local(23, 45), late, None) is True
    assert is_due(local(0, 10, number=12), late, None) is False


# ---------- название ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Заголовок  ", "Заголовок"),
        ("строка один\nстрока два\t\tтри", "строка один строка два три"),
        ("a\u202eb\u200bc\x00d", "abcd"),
        ("Видео 🎬", "Видео 🎬"),
        ("", "Без названия"),
        (None, "Без названия"),
        (" \n\t ", "Без названия"),
    ],
)
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


def test_long_title_is_truncated():
    assert clean_title("а" * 150) == "а" * 99 + "…"


# ---------- выбор материалов ----------


def test_pick_orders_planned_first_then_oldest_and_skips_done(session):
    user = make_user(session)
    other = make_user(session, "b@example.com")
    add_content(session, user, "u-old", "unseen", day(1))
    add_content(session, user, "p-new", "planned", day(9))
    add_content(session, user, "p-old", "planned", day(2))
    add_content(session, user, "u-new", "unseen", day(8))
    add_content(session, user, "done", "studied", day(1))
    add_content(session, user, "meh", "irrelevant", day(1))
    add_content(session, other, "чужой", "planned", day(1))

    items, pending = pick_materials(session, user.id)
    assert [title for _, title in items] == ["p-old", "p-new", "u-old", "u-new"]
    assert pending == 4


def test_pick_is_limited_and_reports_the_rest(session):
    user = make_user(session)
    for number in range(1, 9):
        add_content(session, user, f"m{number}", "unseen", day(number))
    items, pending = pick_materials(session, user.id)
    assert [title for _, title in items] == [f"m{n}" for n in range(1, DIGEST_SIZE + 1)]
    assert pending == 8


def test_pick_nothing_when_nothing_waits(session):
    user = make_user(session)
    add_content(session, user, "done", "studied")
    assert pick_materials(session, user.id) == ([], 0)


# ---------- письмо ----------


def test_email_has_titles_links_and_unsubscribe_link():
    subject, body = build_digest_email(7, [(11, "Первый"), (12, "Второй\nс переводом")], 5)
    assert "Teleiosis" in subject
    assert "1. Первый" in body
    assert "2. Второй с переводом" in body
    assert f"{ORIGIN}/app/item.html?id=11" in body
    assert f"{ORIGIN}/app/item.html?id=12" in body
    assert "И ещё 3 в библиотеке" in body
    assert f"{ORIGIN}/app/unsubscribe.html#token=7." in body


def test_email_without_the_rest_line():
    _, body = build_digest_email(7, [(11, "Единственный")], 1)
    assert "И ещё" not in body


# ---------- захват ----------


def test_claim_is_atomic_per_local_day(session):
    user = make_user(session)
    today = date(2026, 11, 11)
    assert claim_digest(session, user.id, today) is True
    assert claim_digest(session, user.id, today) is False
    assert claim_digest(session, user.id, date(2026, 11, 12)) is True
    assert claim_digest(session, user.id, today) is False  # более ранний день не занять


def test_claim_refuses_after_unsubscribe_or_without_verified_email(session):
    unsubscribed = make_user(session, "a@example.com", enabled=False)
    unverified = make_user(session, "b@example.com", verified=False)
    today = date(2026, 11, 11)
    assert claim_digest(session, unsubscribed.id, today) is False
    assert claim_digest(session, unverified.id, today) is False
    session.refresh(unsubscribed)
    assert unsubscribed.last_digest_on is None


# ---------- проход воркера ----------


def test_sends_when_due(session):
    user = make_user(session)
    add_content(session, user, "Первый", "planned")
    outbox = Outbox()

    report = run(session, outbox)
    assert (report.sent, report.failed) == (1, 0)
    call = outbox.calls[0]
    assert call["to"] == "a@example.com"
    assert "Первый" in call["body"]
    assert call["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert call["headers"]["List-Unsubscribe"].startswith("<http")
    session.refresh(user)
    assert user.last_digest_on == date(2026, 11, 11)


def test_not_before_the_time_and_not_after_the_window(session):
    user = make_user(session)
    add_content(session, user)
    outbox = Outbox()
    assert run(session, outbox, now=NOW - timedelta(hours=1)).sent == 0  # 08:30
    assert run(session, outbox, now=NOW + timedelta(hours=3)).sent == 0  # 12:30
    assert outbox.calls == []
    session.refresh(user)
    assert user.last_digest_on is None


def test_second_pass_on_the_same_day_sends_nothing(session):
    user = make_user(session)
    add_content(session, user)
    outbox = Outbox()
    assert run(session, outbox).sent == 1
    assert run(session, outbox).sent == 0
    assert run(session, outbox, now=NOW + timedelta(minutes=45)).sent == 0
    assert len(outbox.calls) == 1


def test_next_local_day_sends_again(session):
    user = make_user(session)
    add_content(session, user)
    outbox = Outbox()
    run(session, outbox)
    assert run(session, outbox, now=NOW + timedelta(days=1)).sent == 1
    session.refresh(user)
    assert user.last_digest_on == date(2026, 11, 12)


def test_each_user_is_judged_in_their_own_timezone(session):
    moscow = make_user(session, "m@example.com", tz="Europe/Moscow")
    vladivostok = make_user(session, "v@example.com", tz="Asia/Vladivostok")
    add_content(session, moscow)
    add_content(session, vladivostok)
    outbox = Outbox()

    run(session, outbox)  # Москва 09:30, Владивосток 16:30
    assert outbox.recipients == ["m@example.com"]
    # В 23:30 UTC во Владивостоке 09:30 следующего дня, в Москве 02:30
    run(session, outbox, now=datetime(2026, 11, 11, 23, 30, tzinfo=timezone.utc))
    assert outbox.recipients == ["m@example.com", "v@example.com"]


def test_users_who_cannot_receive_mail_are_skipped(session):
    unverified = make_user(session, "a@example.com", verified=False)
    disabled = make_user(session, "b@example.com", enabled=False)
    telegram_only = User(telegram_id=5, timezone="Europe/Moscow")
    session.add(telegram_only)
    session.flush()
    for user in (unverified, disabled, telegram_only):
        add_content(session, user)
    outbox = Outbox()
    assert run(session, outbox).sent == 0
    assert outbox.calls == []


def test_empty_library_does_not_consume_the_day(session):
    user = make_user(session)
    outbox = Outbox()
    assert run(session, outbox).sent == 0
    session.refresh(user)
    assert user.last_digest_on is None

    add_content(session, user, "Новый")
    assert run(session, outbox, now=NOW + timedelta(minutes=1)).sent == 1


def test_only_finished_materials_means_no_mail(session):
    user = make_user(session)
    add_content(session, user, "a", "studied")
    add_content(session, user, "b", "irrelevant")
    outbox = Outbox()
    assert run(session, outbox).sent == 0
    session.refresh(user)
    assert user.last_digest_on is None


def test_failed_send_is_not_retried(session):
    user = make_user(session)
    add_content(session, user)
    outbox = Outbox(result=False)
    report = run(session, outbox)
    assert (report.sent, report.failed) == (0, 1)
    session.refresh(user)
    assert user.last_digest_on == date(2026, 11, 11)  # at-most-once
    assert run(session, outbox, now=NOW + timedelta(minutes=1)).failed == 0
    assert len(outbox.calls) == 1


def test_crash_while_sending_does_not_stop_other_users(session):
    bad = make_user(session, "bad@example.com")
    good = make_user(session, "good@example.com")
    add_content(session, bad)
    add_content(session, good)
    outbox = Outbox(raise_for={"bad@example.com"})
    report = run(session, outbox)
    assert (report.sent, report.failed) == (1, 1)
    assert outbox.recipients == ["good@example.com"]


def test_batch_limit(session):
    for number in range(3):
        user = make_user(session, f"u{number}@example.com")
        add_content(session, user)
    outbox = Outbox()
    assert run(session, outbox, limit=2).sent == 2
    assert run(session, outbox, limit=2).sent == 1
    assert len(outbox.calls) == 3
    assert len(set(outbox.recipients)) == 3


def test_unknown_timezone_falls_back_to_utc(session):
    user = make_user(session, tz="Europe/Nowhere")
    add_content(session, user)
    outbox = Outbox()
    # 09:30 по UTC, подборка на 09:00
    assert run(session, outbox, now=datetime(2026, 11, 11, 9, 30, tzinfo=timezone.utc)).sent == 1


def test_missing_secret_key_stops_the_pass_and_keeps_the_day(session, monkeypatch):
    user = make_user(session)
    add_content(session, user)
    monkeypatch.setattr(settings, "secret_key", "")
    outbox = Outbox()
    with pytest.raises(SecretKeyMissing):
        run(session, outbox)
    assert outbox.calls == []
    session.refresh(user)
    assert user.last_digest_on is None