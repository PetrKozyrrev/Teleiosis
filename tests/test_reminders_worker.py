from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import Content, Reminder, User
from app.reminders import claim_reminder, process_due_reminders
from app.unsubscribe import SecretKeyMissing
from tests.helpers import ORIGIN

NOW = datetime(2026, 11, 11, 6, 30, tzinfo=timezone.utc)


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


def make_user(session, email="a@example.com", verified=True, enabled=True):
    user = User(
        email=email,
        reminders_enabled=enabled,
        email_verified_at=NOW if verified else None,
    )
    session.add(user)
    session.flush()
    return user


def add_content(session, user, title="Материал", status="unseen"):
    row = Content(user_id=user.id, title=title, note="текст", status=status)
    session.add(row)
    session.flush()
    return row


def add_reminder(session, user, content, at, status="pending"):
    row = Reminder(user_id=user.id, content_id=content.id, scheduled_at=at, status=status)
    session.add(row)
    session.flush()
    return row


def run(session, outbox, now=NOW, **kwargs):
    return process_due_reminders(session, now, send=outbox, **kwargs)


def status_of(session, reminder):
    session.refresh(reminder)
    return reminder.status


def test_due_reminder_is_sent(session):
    user = make_user(session)
    content = add_content(session, user, "Статья про рассылки")
    reminder = add_reminder(session, user, content, NOW - timedelta(minutes=5))
    outbox = Outbox()

    report = run(session, outbox)
    assert (report.sent, report.failed, report.cancelled) == (1, 0, 0)
    call = outbox.calls[0]
    assert call["to"] == "a@example.com"
    assert "Статья про рассылки" in call["subject"]
    assert f"{ORIGIN}/app/item.html?id={content.id}" in call["body"]
    assert f"{ORIGIN}/app/unsubscribe.html#token={user.id}." in call["body"]
    assert call["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert status_of(session, reminder) == "sent"


def test_future_reminder_waits_and_exact_time_is_due(session):
    user = make_user(session)
    waiting = add_reminder(session, user, add_content(session, user, "a"), NOW + timedelta(minutes=1))
    exact = add_reminder(session, user, add_content(session, user, "b"), NOW)
    outbox = Outbox()
    assert run(session, outbox).sent == 1
    assert status_of(session, waiting) == "pending"
    assert status_of(session, exact) == "sent"


def test_old_reminder_is_still_sent(session):
    user = make_user(session)
    add_reminder(session, user, add_content(session, user), NOW - timedelta(days=30))
    outbox = Outbox()
    assert run(session, outbox).sent == 1


def test_not_sent_twice(session):
    user = make_user(session)
    add_reminder(session, user, add_content(session, user), NOW - timedelta(minutes=1))
    outbox = Outbox()
    assert run(session, outbox).sent == 1
    assert run(session, outbox, now=NOW + timedelta(minutes=5)).sent == 0
    assert len(outbox.calls) == 1


def test_blocked_users_wait_until_they_can_receive_mail(session):
    unverified = make_user(session, "a@example.com", verified=False)
    disabled = make_user(session, "b@example.com", enabled=False)
    telegram_only = User(telegram_id=5)
    session.add(telegram_only)
    session.flush()
    rows = [
        add_reminder(session, user, add_content(session, user), NOW - timedelta(minutes=1))
        for user in (unverified, disabled, telegram_only)
    ]
    outbox = Outbox()
    assert run(session, outbox).sent == 0
    assert [status_of(session, row) for row in rows] == ["pending"] * 3

    unverified.email_verified_at = NOW
    disabled.reminders_enabled = True
    session.flush()
    assert run(session, outbox).sent == 2
    assert sorted(outbox.recipients) == ["a@example.com", "b@example.com"]


@pytest.mark.parametrize("done", ["studied", "irrelevant"])
def test_finished_material_cancels_the_reminder_without_mail(session, done):
    user = make_user(session)
    reminder = add_reminder(
        session, user, add_content(session, user, status=done), NOW - timedelta(minutes=1)
    )
    outbox = Outbox()
    report = run(session, outbox)
    assert (report.sent, report.cancelled) == (0, 1)
    assert outbox.calls == []
    assert status_of(session, reminder) == "cancelled"


def test_planned_material_still_gets_the_reminder(session):
    user = make_user(session)
    add_reminder(session, user, add_content(session, user, status="planned"), NOW)
    outbox = Outbox()
    assert run(session, outbox).sent == 1


def test_failed_send_is_not_retried(session):
    user = make_user(session)
    reminder = add_reminder(session, user, add_content(session, user), NOW - timedelta(minutes=1))
    outbox = Outbox(result=False)
    report = run(session, outbox)
    assert (report.sent, report.failed) == (0, 1)
    assert status_of(session, reminder) == "sent"  # at-most-once
    assert run(session, outbox, now=NOW + timedelta(minutes=1)).failed == 0
    assert len(outbox.calls) == 1


def test_crash_while_sending_does_not_stop_the_others(session):
    bad = make_user(session, "bad@example.com")
    good = make_user(session, "good@example.com")
    bad_reminder = add_reminder(session, bad, add_content(session, bad), NOW - timedelta(minutes=2))
    add_reminder(session, good, add_content(session, good), NOW - timedelta(minutes=1))
    outbox = Outbox(raise_for={"bad@example.com"})
    report = run(session, outbox)
    assert (report.sent, report.failed) == (1, 1)
    assert outbox.recipients == ["good@example.com"]
    assert status_of(session, bad_reminder) == "sent"


def test_oldest_first_and_batch_limit(session):
    user = make_user(session)
    titles = {}
    for number, minutes in enumerate((30, 10, 20)):
        content = add_content(session, user, f"m{number}")
        add_reminder(session, user, content, NOW - timedelta(minutes=minutes))
        titles[minutes] = f"m{number}"
    outbox = Outbox()
    assert run(session, outbox, limit=2).sent == 2
    assert [titles[30] in outbox.calls[0]["subject"], titles[20] in outbox.calls[1]["subject"]] == [True, True]
    assert run(session, outbox, limit=2).sent == 1
    assert titles[10] in outbox.calls[2]["subject"]


def test_subject_is_one_clean_line(session):
    user = make_user(session)
    add_reminder(session, user, add_content(session, user, "Первая\nвторая\u202eстрока"), NOW)
    outbox = Outbox()
    run(session, outbox)
    subject = outbox.calls[0]["subject"]
    assert subject.startswith("Teleiosis: напоминание: ")
    assert "\n" not in subject and "\r" not in subject and "\u202e" not in subject


def test_missing_secret_key_stops_the_pass_and_keeps_the_reminder(session, monkeypatch):
    user = make_user(session)
    reminder = add_reminder(session, user, add_content(session, user), NOW - timedelta(minutes=1))
    monkeypatch.setattr(settings, "secret_key", "")
    outbox = Outbox()
    with pytest.raises(SecretKeyMissing):
        run(session, outbox)
    assert outbox.calls == []
    assert status_of(session, reminder) == "pending"


def test_claim_is_atomic_and_rechecks_the_user(session):
    user = make_user(session)
    reminder = add_reminder(session, user, add_content(session, user), NOW)
    assert claim_reminder(session, reminder.id) is True
    assert claim_reminder(session, reminder.id) is False

    other = make_user(session, "b@example.com", enabled=False)
    blocked = add_reminder(session, other, add_content(session, other), NOW)
    assert claim_reminder(session, blocked.id) is False
    assert status_of(session, blocked) == "pending"