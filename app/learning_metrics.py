"""Pilot-only aggregates over confirmed events, with explicit observation windows."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LearningEvent, User, UserActivity
from app.stats import calendar_week_start, user_zone

WEEK = timedelta(days=7)
LEARNING_ACTIVITY = {"material_studied", "review_completed"}


def compute_learning_metrics(db: Session, now: datetime) -> dict:
    events = db.scalars(select(LearningEvent).where(LearningEvent.occurred_at <= now)
                        .order_by(LearningEvent.occurred_at, LearningEvent.id)).all()
    zones = dict(db.execute(select(User.id, User.timezone)).all())
    events = [event for event in events if event.user_id in zones]
    registrations = {event.user_id: event for event in events if event.name == "registration_completed"}
    saved = {(event.user_id, event.material_id): event for event in events if event.name == "material_saved"}
    studied = {(event.user_id, event.material_id): event for event in events if event.name == "material_studied"}
    study_pairs = {key: (saved[key], event) for key, event in studied.items()
                   if key in saved and saved[key].occurred_at <= event.occurred_at}

    weekly_learners = set()
    study_times = defaultdict(list)
    for (owner, _), (saving, studying) in study_pairs.items():
        today = now.astimezone(user_zone(zones[owner])).date()
        if calendar_week_start(today) <= studying.local_day <= today:
            weekly_learners.add(owner)
        registration = registrations.get(owner)
        if registration and saving.occurred_at >= registration.occurred_at:
            study_times[owner].append(studying.occurred_at)

    mature_accounts = {owner: event for owner, event in registrations.items() if event.occurred_at + WEEK <= now}
    activated = sum(any(moment < registration.occurred_at + WEEK for moment in study_times[owner])
                    for owner, registration in mature_accounts.items())
    mature_materials = {key: event for key, event in saved.items() if event.occurred_at + WEEK <= now}
    saved_to_study = sum(key in study_pairs and studied[key].occurred_at < event.occurred_at + WEEK
                        for key, event in mature_materials.items())
    first_study_hours = [(min(moments) - registrations[owner].occurred_at).total_seconds() / 3600
                         for owner, moments in study_times.items() if moments]

    product_days = defaultdict(set)
    for owner, day in db.execute(select(UserActivity.user_id, UserActivity.day)):
        product_days[owner].add(day)
    learning_days = defaultdict(set)
    visits = defaultdict(set)
    shown = set()
    opened = set()
    for event in events:
        owner = event.user_id
        if event.name != "registration_completed":
            product_days[owner].add(event.local_day)
        if event.name in LEARNING_ACTIVITY:
            learning_days[owner].add(event.local_day)
        registration = mature_accounts.get(owner)
        if (registration and event.visit_id
                and registration.occurred_at <= event.occurred_at < registration.occurred_at + WEEK):
            visits[owner].add(event.visit_id)
        selection = (owner, event.visit_id, event.budget_minutes)
        if event.name == "time_budget_selected" and event.has_results:
            shown.add(selection)
        elif event.name == "recommendation_opened":
            opened.add(selection)

    retention = {}
    for offset in (7, 30):
        targets = {}
        for owner, registration in registrations.items():
            target = registration.local_day + timedelta(days=offset)
            today = now.astimezone(user_zone(zones[owner])).date()
            if target < today:
                targets[owner] = target
        retention[offset] = {
            "cohort": len(targets),
            "product": sum(day in product_days[owner] for owner, day in targets.items()),
            "learning": sum(day in learning_days[owner] for owner, day in targets.items()),
        }

    return {
        "observed_since": events[0].occurred_at.date() if events else None,
        "events": dict(sorted(Counter(event.name for event in events).items())),
        "weekly_active_learners": len(weekly_learners),
        "activation_7d": (activated, len(mature_accounts)),
        "save_to_study_7d": (saved_to_study, len(mature_materials)),
        "first_study_hours_median": round(median(first_study_hours), 1) if first_study_hours else None,
        "first_study_sample": len(first_study_hours),
        "another_mobile_visit_7d": (sum(len(ids) > 1 for ids in visits.values()), len(visits)),
        "recommendations_started": (len(shown & opened), len(shown)),
        "retention": retention,
    }


def format_learning_report(metrics: dict) -> str:
    def ratio(values):
        part, whole = values
        return f"{part} из {whole} ({round(100 * part / whole)}%)" if whole else "нет данных"

    median_hours = metrics["first_study_hours_median"]
    since = metrics["observed_since"] or "нет данных"
    lines = [
        f"Teleiosis: учебные метрики, начало наблюдения (UTC) — {since}",
        "Учились на текущей локальной неделе: " + (
            str(metrics["weekly_active_learners"]) if metrics["observed_since"] else "нет данных"
        ),
        f"Активация за 7 дней: {ratio(metrics['activation_7d'])}",
        f"Изучены за 7 дней после сохранения: {ratio(metrics['save_to_study_7d'])}",
        f"Повторный мобильный визит за 7 дней: {ratio(metrics['another_mobile_visit_7d'])}",
        f"Открыли рекомендацию после подбора: {ratio(metrics['recommendations_started'])}",
        "Медиана до первого изучения: " + (
            f"{median_hours} ч, выборка {metrics['first_study_sample']}" if median_hours is not None else "нет данных"
        ),
    ]
    for day, values in metrics["retention"].items():
        lines.append(f"D{day}: продукт {ratio((values['product'], values['cohort']))}, "
                     f"обучение {ratio((values['learning'], values['cohort']))}")
    lines.extend(f"{name}: {count}" for name, count in metrics["events"].items())
    return "\n".join(lines)
