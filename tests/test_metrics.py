from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

import app.metrics as metrics_module
from app.metrics import compute_metrics, format_report, return_windows
from app.models import Content, Reminder, User, UserActivity

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def utc(year, month, day, hour=12):
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


def by_name(windows):
    return {w["name"]: (w["cohort"], w["returned"]) for w in windows}


# ---------- окна возврата ----------


def test_windows_use_days_after_registration():
    users = [
        (1, utc(2026, 10, 1), "UTC"),  # вернулся в дни 3 и 11
        (2, utc(2026, 10, 1), "UTC"),  # не возвращался
        (3, utc(2026, 11, 10), "UTC"),  # слишком свежий для любого окна
    ]
    activity = {1: {date(2026, 10, 4), date(2026, 10, 12)}, 3: {date(2026, 11, 11)}}
    result = by_name(return_windows(users, activity, NOW))
    assert result["В течение 7 дней (дни 1-7)"] == (2, 1)
    assert result["На второй неделе (дни 8-14)"] == (2, 1)
    assert result["В течение 30 дней (дни 1-30)"] == (2, 1)
    assert result["Ровно на 7-й день (D7)"] == (2, 0)
    assert result["Ровно на 30-й день (D30)"] == (2, 0)


def test_exact_day_windows():
    users = [(1, utc(2026, 10, 1), "UTC")]
    activity = {1: {date(2026, 10, 8), date(2026, 10, 31)}}  # день 7 и день 30
    result = by_name(return_windows(users, activity, NOW))
    assert result["Ровно на 7-й день (D7)"] == (1, 1)
    assert result["Ровно на 30-й день (D30)"] == (1, 1)


def test_registration_day_activity_is_not_a_return():
    users = [(1, utc(2026, 10, 1), "UTC")]
    activity = {1: {date(2026, 10, 1)}}
    result = by_name(return_windows(users, activity, NOW))
    assert result["В течение 7 дней (дни 1-7)"] == (1, 0)


def test_window_counts_only_after_it_has_fully_passed():
    users = [(1, utc(2026, 11, 5), "UTC")]
    activity = {1: {date(2026, 11, 8)}}
    # 12.11: прошло 7 дней, день 7 ещё не закончился
    assert by_name(return_windows(users, activity, NOW))["В течение 7 дней (дни 1-7)"] == (0, 0)
    next_day = NOW + timedelta(days=1)
    assert by_name(return_windows(users, activity, next_day))["В течение 7 дней (дни 1-7)"] == (1, 1)


def test_registration_day_is_local():
    # 31.10 20:00 UTC во Владивостоке уже 1.11: день 1 это 2.11
    users = [(1, datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc), "Asia/Vladivostok")]
    result = by_name(return_windows(users, {1: {date(2026, 11, 2)}}, NOW))
    assert result["В течение 7 дней (дни 1-7)"] == (1, 1)
    result = by_name(return_windows(users, {1: {date(2026, 11, 1)}}, NOW))
    assert result["В течение 7 дней (дни 1-7)"] == (1, 0)


def test_empty_cohorts():
    result = by_name(return_windows([], {}, NOW))
    assert all(value == (0, 0) for value in result.values())


# ---------- отчёт по базе ----------


def make_site_user(session, email, created):
    user = User(email=email, timezone="UTC", email_verified_at=created, reminders_enabled=True)
    session.add(user)
    session.flush()
    session.execute(
        text("UPDATE users SET created_at = :ts WHERE id = :id"), {"ts": created, "id": user.id}
    )
    return user


def add_content(session, user, status="unseen", **fields):
    row = Content(user_id=user.id, title="Материал", status=status, **fields)
    if "url" not in fields:
        row.note = "текст"
    session.add(row)
    session.flush()
    return row


def test_compute_metrics_and_report(session):
    active = make_site_user(session, "active@example.com", utc(2026, 10, 1))
    make_site_user(session, "quiet@example.com", utc(2026, 10, 1))
    telegram = User(telegram_id=9)
    session.add(telegram)
    session.flush()

    for _ in range(3):
        add_content(session, active, "studied")
    link = add_content(
        session, active, "unseen",
        url="https://example.com/a", url_normalized="https://example.com/a", open_count=1,
    )
    for _ in range(5):  # материалы Telegram-пользователя в отчёт не входят
        add_content(session, telegram, "studied")

    session.add_all(
        [
            UserActivity(user_id=active.id, day=date(2026, 10, 3)),
            UserActivity(user_id=active.id, day=date(2026, 11, 10)),
            UserActivity(user_id=active.id, day=date(2026, 10, 9)),
            Reminder(user_id=active.id, content_id=link.id, scheduled_at=utc(2026, 12, 1), status="pending"),
            Reminder(user_id=active.id, content_id=link.id, scheduled_at=utc(2026, 11, 1), status="sent"),
        ]
    )
    session.flush()

    metrics = compute_metrics(session, NOW)
    assert metrics["registered"] == 2
    assert metrics["activated"] == 1
    assert metrics["verified"] == 2
    assert metrics["active_7d"] == 1
    assert metrics["materials_total"] == 4
    assert metrics["by_status"]["studied"] == 3
    assert (metrics["with_url"], metrics["opened"], metrics["users_opened"]) == (1, 1, 1)
    assert metrics["regular_studied"] == 1
    assert metrics["reminders_by_status"] == {"pending": 1, "sent": 1, "cancelled": 0}
    assert metrics["users_set_reminder"] == 1
    assert by_name(metrics["returns"])["В течение 7 дней (дни 1-7)"] == (2, 1)

    report = format_report(metrics)
    assert "Зарегистрировано: 2" in report
    assert "Активировано (сохранили хотя бы 1 материал): 1 из 2 (50%)" in report
    assert "Доля изученных (без неактуальных): 3 из 4 (75%)" in report
    assert "цель 20%: достигнута" in report
    assert "На второй неделе (дни 8-14): 1 из 2 (50%)" in report
    assert "цель 50%: достигнута" in report
    assert "@" not in report  # ни одного e-mail


def test_report_for_an_empty_system(session):
    report = format_report(compute_metrics(session, NOW))
    assert "Зарегистрировано: 0" in report
    assert "нет данных" in report
    assert "@" not in report


def test_module_is_safe_to_import():
    assert callable(metrics_module.main)