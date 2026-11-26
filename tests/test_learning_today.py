from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Content, ReviewCard, StudyGoal, StudyTask, User
from app import stats
from app.routers import learning, review
from app.sessions import create_session

PATH = "/mobile/learning/today"
NOW = datetime(2026, 11, 22, 22, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def freeze_today(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)

    monkeypatch.setattr(learning, "datetime", Frozen)
    monkeypatch.setattr(stats, "datetime", Frozen)
    monkeypatch.setattr(review, "datetime", Frozen)


def owner(session, email="learning@example.com", zone="Europe/Moscow"):
    user = User(email=email, timezone=zone, weekly_reading_goal=4)
    session.add(user)
    session.flush()
    token, _ = create_session(session, user, client_type="mobile")
    return user, {"Authorization": f"Bearer {token}"}


def material(session, user, name, status="unseen", **fields):
    entry = Content(user_id=user.id, title=name, status=status, **({"note": name} | fields))
    session.add(entry)
    session.flush()
    return entry


def task(session, goal, entry, day, priority=1):
    item = StudyTask(user_id=goal.user_id, goal_id=goal.id, content_id=entry.id,
                     day=date.fromisoformat(day), priority=priority, minutes=25)
    session.add(item)
    session.flush()
    return item


def goal_for(session, user):
    goal = StudyGoal(user_id=user.id, name="Synthetic goal")
    session.add(goal)
    session.flush()
    return goal


def test_selection_orders_overdue_before_today_by_date_priority_and_id(session):
    user, _ = owner(session)
    goal = goal_for(session, user)
    entries = [task(session, goal, material(session, user, str(i), status), day, priority)
               for i, (day, priority, status) in enumerate([
                   ("2026-11-23", 1, "unseen"),
                   ("2026-11-12", 3, "planned"),
                   ("2026-11-12", 2, "studied"),
                   ("2026-11-12", 2, "unseen"),
                   ("2026-11-11", 1, "irrelevant"),
               ])]
    day = date(2026, 11, 23)
    action, state = learning.select_next_action(session, user.id, day)
    assert (action.task_id, action.reason, action.duration_minutes, state) == (
        entries[2].id, "studied_task", 25, "available",
    )
    assert session.get(Content, action.material_id).status == "studied"

    for entry, expected, reason in [
        (entries[2], entries[3], "overdue_task"),
        (entries[3], entries[1], "overdue_task"),
        (entries[1], entries[0], "today_task"),
    ]:
        entry.completed_at = NOW
        session.flush()
        action, _ = learning.select_next_action(session, user.id, day)
        assert (action.task_id, action.reason) == (expected.id, reason)


def test_fallback_prefers_planned_then_oldest_unseen_and_leaves_future_tasks_out(session):
    user, _ = owner(session)
    day = date(2026, 11, 23)
    assert learning.select_next_action(session, user.id, day) == (None, "empty")
    studied = material(session, user, "Studied", "studied")
    material(session, user, "Irrelevant", "irrelevant")
    assert learning.select_next_action(session, user.id, day) == (None, "no_recommendation")

    goal = goal_for(session, user)
    reserved = material(session, user, "Reserved", "planned")
    task(session, goal, reserved, "2026-11-24")
    assert learning.select_next_action(session, user.id, day) == (None, "scheduled_later")

    early = datetime(2026, 10, 1, tzinfo=timezone.utc)
    oldest = material(session, user, "Unknown time", note=None, url="https://example.com/article", created_at=early)
    material(session, user, "Same timestamp", created_at=early)
    planned = material(session, user, "Read later", "planned", note="x" * 1001)
    action, _ = learning.select_next_action(session, user.id, day)
    assert (action.material_id, action.reason, action.duration_minutes) == (planned.id, "planned_material", 2)
    planned.status = studied.status
    session.flush()
    action, _ = learning.select_next_action(session, user.id, day)
    assert (action.material_id, action.reason, action.duration_minutes) == (oldest.id, "unseen_material", None)
    oldest.video_duration_seconds = 61
    assert learning.material_action(oldest, "unseen_material").duration_minutes == 2


def test_today_scopes_every_section_and_uses_the_same_local_day(client, session):
    assert client.get(PATH).status_code == 401
    user, headers = owner(session)
    other, other_headers = owner(session, "other@example.com", "UTC")
    entry = material(session, user, "Own material", "studied", studied_at=NOW)
    own_task = task(session, goal_for(session, user), entry, "2026-11-23")
    other_entry = material(session, other, "Other material")
    task(session, goal_for(session, other), other_entry, "2026-11-10")
    session.add_all([
        ReviewCard(user_id=owner_id, content_id=entry_id, question="Q", answer="A", due_on=date.fromisoformat(day), paused=paused)
        for owner_id, entry_id, day, paused in [
            (user.id, entry.id, "2026-11-23", False),
            (user.id, entry.id, "2026-11-24", False),
            (user.id, entry.id, "2026-11-23", True),
            (other.id, other_entry.id, "2026-11-22", False),
            (other.id, other_entry.id, "2026-11-23", False),
        ]
    ])
    session.flush()
    result = client.get(PATH, headers=headers)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json() == {
        "local_date": "2026-11-23", "timezone": "Europe/Moscow",
        "next_action": {"material_id": entry.id, "title": entry.title, "source": "other",
                        "content_type": "other", "reason": "studied_task", "task_id": own_task.id,
                        "duration_minutes": 25, "task_day": "2026-11-23"},
        "library_state": "available", "due_review_count": 1,
        "weekly_progress": {"week_start": "2026-11-23", "weekly_goal": 4, "weekly_completed": 1,
                            "tasks_total": 1, "tasks_done": 0},
    }
    another = client.get(PATH, headers=other_headers).json()
    assert another["local_date"] == "2026-11-22"
    assert another["next_action"]["material_id"] == other_entry.id
    assert another["due_review_count"] == 1
    assert another["weekly_progress"]["weekly_completed"] == 0
    assert another["weekly_progress"]["tasks_total"] == 0
    reading = client.get("/mobile/reading-progress", headers=headers).json()
    assert reading["weekly_completed"] == result.json()["weekly_progress"]["weekly_completed"]
    assert client.get("/mobile/review", headers=headers).json()["total"] == result.json()["due_review_count"]

    changed_zone = client.patch("/me/settings", headers=headers, json={"timezone": "UTC"})
    assert changed_zone.status_code == 200
    changed = client.get(PATH, headers=headers).json()
    assert changed["local_date"] == "2026-11-22"
    assert changed["next_action"] is None
    assert changed["due_review_count"] == 0
    assert client.patch("/me/settings", headers=headers, json={"timezone": "Europe/Moscow"}).status_code == 200

    moved = client.put(f"/mobile/plan/tasks/{own_task.id}/day",
                       json={"day": "2026-11-24"}, headers=headers | {"If-Match": '"1"'})
    assert moved.status_code == 200
    future = client.get(PATH, headers=headers).json()
    assert future["next_action"] is None
    assert future["library_state"] == "scheduled_later"

    completed = client.put(f"/mobile/plan/tasks/{own_task.id}/complete", headers=headers | {"If-Match": '"2"'})
    assert completed.status_code == 200
    updated = client.get(PATH, headers=headers).json()
    assert updated["library_state"] == "no_recommendation"
    assert updated["weekly_progress"]["tasks_done"] == 1
    assert session.scalar(select(Content.status).where(Content.id == entry.id)) == "studied"
