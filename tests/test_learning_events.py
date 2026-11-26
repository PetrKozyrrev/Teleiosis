from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.config import settings
from app.learning_events import record_learning_event
from app.learning_metrics import compute_learning_metrics, format_learning_report
from app.models import LearningEvent, User, UserActivity
from tests.helpers import auth_headers as auth

PATH = "/mobile/learning/events"


@pytest.fixture
def pilot(monkeypatch):
    monkeypatch.setattr(settings, "learning_metrics_enabled", True)


def test_disabled_flag_persists_no_events(client, session):
    assert client.post(PATH, headers=auth(1) | {"Idempotency-Key": str(uuid4())},
                       json={"name": "today_viewed", "visit_id": str(uuid4())}).status_code == 204
    assert client.post("/contents", headers=auth(1), json={"note": "Private note"}).status_code == 201
    assert session.scalar(select(func.count()).select_from(LearningEvent)) == 0


def test_failed_event_insert_preserves_the_material_transaction(client, session, pilot, caplog):
    session.execute(text("ALTER TABLE learning_events RENAME TO unavailable_events"))

    response = client.post("/contents", headers=auth(1), json={"note": "Keep this material"})

    assert response.status_code == 201
    assert client.get(f"/contents/{response.json()['id']}", headers=auth(1)).json()["note"] == "Keep this material"
    assert "learning event write failed: ProgrammingError" in caplog.text
    assert "Keep this material" not in caplog.text
    session.execute(text("ALTER TABLE unavailable_events RENAME TO learning_events"))
    assert session.scalar(select(func.count()).select_from(LearningEvent)) == 0


def test_client_events_are_typed_authorized_owner_scoped_and_deduplicated(client, session, pilot):
    headers = {"Idempotency-Key": str(uuid4())}
    body = {"name": "today_viewed", "visit_id": str(uuid4())}
    assert client.post(PATH, headers=headers, json=body).status_code == 401
    for payload in (body | {"title": "must not be accepted"}, body | {"name": "material_studied"},
                    body | {"name": "time_budget_selected", "budget_minutes": 60}):
        response = client.post(PATH, headers=headers | auth(1), json=payload)
        assert response.status_code == 422
        assert "must not be accepted" not in response.text
    for _ in range(2):
        assert client.post(PATH, headers=headers | auth(1), json=body).status_code == 204
    entry = client.post("/contents", headers=auth(2), json={"note": "Foreign"}).json()
    opened = body | {"name": "recommendation_opened", "material_id": entry["id"], "budget_minutes": 15}
    assert client.post(PATH, headers=headers | auth(1), json=opened).status_code == 404
    assert client.post(PATH, headers=headers | auth(2), json=opened).status_code == 204
    items = session.scalars(select(LearningEvent).order_by(LearningEvent.id)).all()
    assert [event.name for event in items] == ["today_viewed", "material_saved", "recommendation_opened"]
    assert items[0].material_id is None and items[-1].material_id == entry["id"]


def test_confirmed_domain_writes_and_retries_do_not_overcount(client, session, pilot):
    registered = client.post("/mobile/auth/register", json={
        "email": "synthetic-e5@example.com", "password": "synthetic-only-password", "consent": True,
    })
    assert registered.status_code == 201
    headers = {"Authorization": "Bearer " + registered.json()["token"]}
    submission = headers | {"Idempotency-Key": str(uuid4())}
    entry = client.post("/contents/submissions", headers=submission, json={"note": "Private note"}).json()
    assert client.post("/contents/submissions", headers=submission, json={"note": "Private note"}).json()["id"] == entry["id"]
    goal = client.post("/mobile/learning/goals", headers=headers, json={"name": "Private goal"}).json()
    assert client.post("/mobile/learning/goals", headers=headers, json={"name": "Private goal"}).json()["id"] == goal["id"]
    for _ in range(2):
        assert client.post(f"/mobile/learning/goals/{goal['id']}/materials", headers=headers,
                           json={"content_id": entry["id"]}).status_code == 204

    path = f"/mobile/learning/materials/{entry['id']}"
    repeat = headers | {"Idempotency-Key": str(uuid4()), "If-Match": f'"{entry["version"]}"'}
    for _ in range(2):
        assert client.post(path + "/completion", headers=repeat, json={}).status_code == 200
        assert client.put(path + "/reflection", headers=headers, json={"thought": "Private thought", "previous": None}).status_code == 200
    content_path = f"/contents/{entry['id']}"
    for status in ("planned", "studied"):
        assert client.patch(content_path, headers=headers, json={"status": status}).status_code == 200

    creation = headers | {"Idempotency-Key": str(uuid4())}
    card_data = {"content_id": entry["id"], "question": "Private question", "answer": "Private answer"}
    card = client.post("/mobile/review", headers=creation, json=card_data).json()
    assert client.post("/mobile/review", headers=creation, json=card_data).json()["id"] == card["id"]
    rating = headers | {"Idempotency-Key": str(uuid4()), "If-Match": f'"{card["version"]}"'}
    for _ in range(2):
        assert client.post(f"/mobile/review/{card['id']}/answers", headers=rating, json={"rating": "again"}).status_code == 200

    counts = dict(session.execute(select(LearningEvent.name, func.count()).group_by(LearningEvent.name)).all())
    assert counts == dict.fromkeys(("registration_completed", "material_saved", "goal_created", "goal_material_linked",
                                  "material_studied", "study_reflection_saved", "review_card_created", "review_completed"), 1)
    assert client.post("/auth/delete-account", headers=headers, json={"password": "synthetic-only-password"}).status_code == 204
    assert session.scalar(select(func.count()).select_from(LearningEvent)) == 0


def test_metrics_use_mature_cohorts_local_week_and_confirmed_selection(session, pilot):
    now = datetime(2026, 11, 25, 17, tzinfo=timezone.utc)
    alice, bob, recent = [User(email=f"{name}@example.com", timezone="Europe/Moscow")
                          for name in ("alice", "bob", "recent")]
    session.add_all([alice, bob, recent])
    session.flush()

    def add(user, name, key, days, hours=0, **fields):
        record_learning_event(session, user, name, key, now=now - timedelta(days=days) + timedelta(hours=hours), **fields)

    add(alice, "registration_completed", 1, 31)
    add(bob, "registration_completed", 1, 10)
    add(recent, "registration_completed", 1, 2)
    add(alice, "material_saved", 1, 31, 1, material_id=1)
    add(alice, "material_studied", 1, 30, 1, material_id=1)
    add(alice, "material_saved", 2, 30, material_id=2)
    add(alice, "material_studied", 2, 2, 5, material_id=2)
    add(bob, "material_saved", 3, 10, material_id=3)
    add(bob, "material_studied", 8, 0, material_id=8)  # Unknown save → excluded from first-study metrics.
    add(recent, "material_saved", 4, 2, material_id=4)
    add(recent, "material_studied", 4, 1, material_id=4)
    visit_a, visit_b = uuid4(), uuid4()
    add(alice, "today_viewed", uuid4(), 31, 2, visit_id=visit_a)
    add(alice, "today_viewed", uuid4(), 30, 2, visit_id=visit_b)
    add(alice, "time_budget_selected", uuid4(), 30, visit_id=visit_b, budget_minutes=15, has_results=True)
    add(alice, "recommendation_opened", uuid4(), 30, 1, visit_id=visit_b, budget_minutes=15, material_id=1)
    add(alice, "time_budget_selected", uuid4(), 30, 1, visit_id=visit_b, budget_minutes=5, has_results=False)
    add(alice, "review_completed", "review", 1)
    session.add(UserActivity(user_id=bob.id, day=(now - timedelta(days=3)).date()))
    session.flush()

    report = compute_learning_metrics(session, now)
    assert report["weekly_active_learners"] == 2
    assert report["activation_7d"] == (1, 2)
    assert report["save_to_study_7d"] == (1, 3)
    assert report["another_mobile_visit_7d"] == (1, 1)
    assert report["recommendations_started"] == (1, 1)
    assert report["first_study_hours_median"] == 24.5 and report["first_study_sample"] == 2
    assert report["retention"][7] == {"cohort": 2, "product": 1, "learning": 0}
    assert report["retention"][30] == {"cohort": 1, "product": 1, "learning": 1}
    assert "@example.com" not in format_learning_report(report)
