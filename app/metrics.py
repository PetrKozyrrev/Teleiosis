"""Метрики закрытого тестирования. Запуск: python -m app.metrics

В отчёте только агрегаты: ни e-mail, ни имён, ни идентификаторов пользователей.
В расчёт входят только пользователи сайта (с e-mail). Активный день это день хотя бы
с одним действием с материалами (см. app/activity.py).

Данные грузятся в память: для закрытого теста (десятки и сотни пользователей) это нормально."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Content, Reminder, User, UserActivity
from app.stats import STATUSES, user_zone

# Цели закрытого тестирования из бизнес-плана
GOAL_RETURN_WEEK_TWO = 0.5  # не меньше 50% пользователей возвращаются на второй неделе
GOAL_REGULAR_STUDIED = 0.2  # не меньше 20% регулярно отмечают материалы изученными
REGULAR_STUDIED_MIN = 3  # «регулярно»: не меньше стольких материалов сейчас в статусе «Изучено»
TESTERS_GOAL = "5-10"


@dataclass(frozen=True)
class Window:
    name: str
    first: int  # первый день окна после дня регистрации
    last: int  # последний день окна


WINDOWS = (
    Window("В течение 7 дней (дни 1-7)", 1, 7),
    Window("На второй неделе (дни 8-14)", 8, 14),
    Window("В течение 30 дней (дни 1-30)", 1, 30),
    Window("Ровно на 7-й день (D7)", 7, 7),
    Window("Ровно на 30-й день (D30)", 30, 30),
)
WEEK_TWO = WINDOWS[1].name


def return_windows(users, activity: dict[int, set[date]], now: datetime) -> list[dict]:
    """users: (id, created_at, timezone). Дни считаются от местной даты регистрации.
    В окно попадают только пользователи, у которых оно уже полностью прошло."""
    result = []
    for window in WINDOWS:
        cohort = returned = 0
        for user_id, created_at, timezone_name in users:
            zone = user_zone(timezone_name)
            registered = created_at.astimezone(zone).date()
            today = now.astimezone(zone).date()
            if (today - registered).days <= window.last:
                continue  # окно ещё не закончилось
            cohort += 1
            days = activity.get(user_id, set())
            if any(
                registered + timedelta(days=offset) in days
                for offset in range(window.first, window.last + 1)
            ):
                returned += 1
        result.append({"name": window.name, "cohort": cohort, "returned": returned})
    return result


def compute_metrics(db: Session, now: datetime) -> dict:
    site_ids = select(User.id).where(User.email.is_not(None))
    users = db.execute(
        select(
            User.id,
            User.created_at,
            User.timezone,
            User.email_verified_at,
            User.reminders_enabled,
        )
        .where(User.email.is_not(None))
        .order_by(User.id)
    ).all()

    activity: dict[int, set[date]] = {}
    activity_rows = db.execute(
        select(UserActivity.user_id, UserActivity.day).where(
            UserActivity.user_id.in_(site_ids)
        )
    )
    for user_id, day in activity_rows:
        activity.setdefault(user_id, set()).add(day)

    active_7d = 0
    for user_id, _created, timezone_name, *_rest in users:
        today = now.astimezone(user_zone(timezone_name)).date()
        days = activity.get(user_id, set())
        if any(today - timedelta(days=offset) in days for offset in range(7)):
            active_7d += 1

    by_status = dict.fromkeys(STATUSES, 0)
    status_rows = db.execute(
        select(Content.status, func.count())
        .where(Content.user_id.in_(site_ids))
        .group_by(Content.status)
    )
    for status_value, amount in status_rows:
        if status_value in by_status:
            by_status[status_value] = amount

    with_url, opened, users_opened = db.execute(
        select(
            func.count(Content.id).filter(Content.url.is_not(None)),
            func.count(Content.id).filter(Content.url.is_not(None), Content.open_count > 0),
            func.count(Content.user_id.distinct()).filter(
                Content.url.is_not(None), Content.open_count > 0
            ),
        ).where(Content.user_id.in_(site_ids))
    ).one()

    activated = db.scalar(
        select(func.count(Content.user_id.distinct())).where(Content.user_id.in_(site_ids))
    )
    regular_subquery = (
        select(Content.user_id)
        .where(Content.user_id.in_(site_ids), Content.status == "studied")
        .group_by(Content.user_id)
        .having(func.count() >= REGULAR_STUDIED_MIN)
        .subquery()
    )
    regular_studied = db.scalar(select(func.count()).select_from(regular_subquery))

    reminders_by_status = dict.fromkeys(("pending", "sent", "cancelled"), 0)
    reminder_rows = db.execute(
        select(Reminder.status, func.count())
        .where(Reminder.user_id.in_(site_ids))
        .group_by(Reminder.status)
    )
    for status_value, amount in reminder_rows:
        if status_value in reminders_by_status:
            reminders_by_status[status_value] = amount
    users_set_reminder = db.scalar(
        select(func.count(Reminder.user_id.distinct())).where(Reminder.user_id.in_(site_ids))
    )

    return {
        "date": now.date(),
        "registered": len(users),
        "activated": activated,
        "verified": sum(1 for user in users if user.email_verified_at is not None),
        "reminders_on": sum(
            1 for user in users if user.reminders_enabled and user.email_verified_at is not None
        ),
        "active_7d": active_7d,
        "materials_total": sum(by_status.values()),
        "by_status": by_status,
        "with_url": with_url,
        "opened": opened,
        "users_opened": users_opened,
        "regular_studied": regular_studied,
        "returns": return_windows([(u[0], u[1], u[2]) for u in users], activity, now),
        "reminders_by_status": reminders_by_status,
        "users_set_reminder": users_set_reminder,
    }


def share_text(part: int, whole: int) -> str:
    if not whole:
        return "нет данных"
    return f"{part} из {whole} ({round(part / whole * 100)}%)"


def goal_text(part: int, whole: int, goal: float) -> str:
    if not whole:
        return ""
    verdict = "достигнута" if part / whole >= goal else "не достигнута"
    return f"  [цель {round(goal * 100)}%: {verdict}]"


def format_report(metrics: dict) -> str:
    m = metrics
    registered = m["registered"]
    studied = m["by_status"]["studied"]
    studied_base = m["materials_total"] - m["by_status"]["irrelevant"]
    average = round(m["materials_total"] / m["activated"], 1) if m["activated"] else 0

    lines = [
        f"Teleiosis: метрики закрытого тестирования на {m['date']} (UTC)",
        "Только пользователи сайта (с e-mail). Персональных данных в отчёте нет.",
        "Активный день: день хотя бы с одним действием (сохранил, изменил, открыл, напоминание).",
        "",
        "Пользователи",
        f"  Зарегистрировано: {registered}",
        f"  Активировано (сохранили хотя бы 1 материал): {share_text(m['activated'], registered)}",
        f"  Подтвердили e-mail: {share_text(m['verified'], registered)}",
        f"  Активны за последние 7 дней: {share_text(m['active_7d'], registered)}"
        f"  [ориентир: тестировщиков {TESTERS_GOAL}]",
        "",
        "Материалы",
        f"  Всего сохранено: {m['materials_total']} (в среднем на активированного: {average})",
        f"  Статусы: не просмотрено {m['by_status']['unseen']}, "
        f"запланировано {m['by_status']['planned']}, изучено {studied}, "
        f"неактуально {m['by_status']['irrelevant']}",
        f"  Доля изученных (без неактуальных): {share_text(studied, studied_base)}",
        f"  Пользователей с {REGULAR_STUDIED_MIN}+ изученными: "
        f"{share_text(m['regular_studied'], registered)}"
        f"{goal_text(m['regular_studied'], registered, GOAL_REGULAR_STUDIED)}",
        f"  Оригинал открывали (материалы со ссылкой): {share_text(m['opened'], m['with_url'])}",
        f"  Пользователей, открывавших оригинал: {share_text(m['users_opened'], registered)}",
        "",
        "Возвраты (активность в днях после дня регистрации; считаются только завершённые окна)",
    ]
    for window in m["returns"]:
        note = ""
        if window["name"] == WEEK_TWO:
            note = goal_text(window["returned"], window["cohort"], GOAL_RETURN_WEEK_TWO)
        lines.append(
            f"  {window['name']}: {share_text(window['returned'], window['cohort'])}{note}"
        )
    sent = m["reminders_by_status"]
    lines += [
        "",
        "Напоминания",
        f"  Напоминания включены и e-mail подтверждён: {share_text(m['reminders_on'], registered)}",
        f"  Напоминаний по материалам: ждут {sent['pending']}, отправлено {sent['sent']}, "
        f"отменено {sent['cancelled']}",
        f"  Пользователей, поставивших хотя бы одно: {share_text(m['users_set_reminder'], registered)}",
        "  Ежедневные подборки отдельно не учитываются (хранится только дата последней).",
        "",
        "Выборка маленькая: проценты ориентировочные. Считать окна возврата стоит, "
        "когда прошли 7 и 14 дней после регистрации тестировщиков.",
    ]
    return "\n".join(lines)


def main() -> None:
    with SessionLocal() as db:
        print(format_report(compute_metrics(db, datetime.now(timezone.utc))))


if __name__ == "__main__":
    main()