from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Content, StudyGoal, StudyTask, StudyTaskEvent, User, WeekBudget
from app.routers.week_plan import summarize
from tests.helpers import auth_headers as auth

PLAN = "/mobile/plan"


def material(client, user=1):
    response = client.post("/contents", headers=auth(user), json={"note": "Synthetic plan material"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def goal(client, name="Synthetic goal", user=1):
    response = client.post(PLAN + "/goals", headers=auth(user), json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def task(client, goal_id, content_id, **changes):
    body = {"day": "2026-11-22", "minutes": 10, "priority": 2, "goal_id": goal_id, "content_id": content_id}
    return client.post(PLAN + "/tasks", headers=auth(1), json=body | changes)


def week(client, day="2026-11-22", user=1):
    response = client.get(PLAN, params={"day": day}, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def versioned(version, user=1):
    return {**auth(user), "If-Match": f'"{version}"'}


def test_empty_week_calendar_and_invalid_dates(client):
    assert client.get(PLAN).status_code == 401
    snapshot = week(client, "2027-01-01")
    assert (snapshot["week"], snapshot["end"]) == ("2026-12-28", "2027-01-03")
    assert snapshot["summary"] == {"total": 0, "done": 0, "planned_minutes": 0, "done_minutes": 0, "next_id": None}
    for day in ("2026-02-30", "0001-01-01", "9999-12-31"):
        assert client.get(PLAN, params={"day": day}, headers=auth(1)).status_code == 422


def test_week_plan_replay_progress_history_and_move(client):
    target, first, second = goal(client), material(client), material(client)
    assert goal(client, "synthetic goal") == target
    a = task(client, target, first).json()
    b = task(client, target, second, minutes=50, priority=1).json()
    assert task(client, target, first).json() == a
    assert task(client, target, first, minutes=5).status_code == 409
    assert week(client)["summary"]["next_id"] == b["id"]
    path = PLAN + f"/tasks/{a['id']}"
    done = client.put(path + "/complete", headers=versioned(1)).json()
    assert done["version"] == 2 and done["completed_at"]
    assert client.put(path + "/complete", headers=versioned(1)).json() == done
    assert client.put(path + "/day", headers=versioned(2), json={"day": "2026-11-23"}).status_code == 409
    assert client.get(f"/contents/{first}", headers=auth(1)).json()["status"] == "unseen"
    assert week(client)["summary"] == {"done": 1, "total": 2, "planned_minutes": 60, "done_minutes": 10, "next_id": b["id"]}
    path = PLAN + f"/tasks/{b['id']}"
    body = {"day": "2026-11-23"}
    assert client.put(path + "/day", headers=versioned(1), json=body).json()["version"] == 2
    assert client.put(path + "/day", headers=versioned(1), json=body).json()["version"] == 2
    assert client.put(path + "/complete", headers=versioned(1)).status_code == 412
    assert client.delete(path, headers=versioned(1)).status_code == 412
    assert week(client)["summary"]["total"] == week(client)["summary"]["done"] == 1
    assert week(client, "2026-11-23")["summary"]["done"] == 0
    exported = client.get("/me/export", headers=auth(1)).json()["study_plan"]
    assert [(e["task_id"], e["kind"]) for e in exported["history"]] == [
        (a["id"], "created"), (a["id"], "completed"), (b["id"], "created"), (b["id"], "moved")]
    assert client.delete(path, headers=versioned(2)).status_code == 204
    assert not week(client, "2026-11-23")["tasks"]


def test_plan_rejects_foreign_rows_and_cascades(client, session):
    target, own, foreign = goal(client), material(client), material(client, 2)
    assert task(client, goal(client, user=2), own).status_code == 404
    assert task(client, target, foreign).status_code == 404
    item = task(client, target, own).json()
    assert client.put(PLAN + f"/tasks/{item['id']}/complete", headers=versioned(1, 2)).status_code == 404
    assert client.delete(PLAN + f"/goals/{target}", headers=auth(2)).status_code == 404
    assert week(client, user=2)["tasks"] == []
    assert not client.get("/me/export", headers=auth(2)).json()["study_plan"]["history"]
    assert client.delete(f"/contents/{own}", headers=auth(1)).status_code == 204
    other = material(client)
    assert task(client, target, other).status_code == 200
    assert client.delete(PLAN + f"/goals/{target}", headers=auth(1)).status_code == 204
    assert not week(client)["tasks"]
    assert session.get(Content, other) is not None
    assert session.scalar(select(StudyTaskEvent.task_id)) is None


def test_budget_compare_and_set_and_account_cleanup(client, session):
    path = PLAN + "/weeks/2026-11-16/budget"
    assert client.put(path, headers=auth(1), json={"minutes": 70, "previous": None}).status_code == 204
    assert client.put(path, headers=auth(1), json={"minutes": 70, "previous": None}).status_code == 204
    assert client.put(path, headers=auth(1), json={"minutes": 80, "previous": None}).status_code == 412
    assert client.put(path, headers=auth(1), json={"minutes": 80, "previous": 70}).status_code == 204
    assert week(client)["budget"] == 80
    assert week(client, user=2)["budget"] is None
    assert week(client, "2026-11-23")["budget"] is None
    target = goal(client)
    task(client, target, material(client))
    session.delete(session.scalar(select(User).where(User.email == "user1@example.com")))
    session.commit()
    for column in (StudyGoal.id, StudyTask.id, StudyTaskEvent.task_id, WeekBudget.week):
        assert session.scalar(select(column)) is None


@pytest.mark.parametrize("bad", [{"minutes": None}, {"minutes": 0}, {"minutes": 1441}, {"priority": 4},
                                  {"day": "2026-11-31"}, {"day": 0}, {"day": "2026-11-22T00:00:00"}, {"user_id": 99}])
def test_missing_duration_and_invalid_inputs_leave_no_task(client, bad):
    assert task(client, goal(client), material(client), **bad).status_code == 422
    assert week(client)["tasks"] == []


def test_summary_priority_ties_are_deterministic():
    tasks = [{"id": i, "priority": 1, "day": date(2026, 11, 22), "minutes": 5, "completed_at": None}
             for i in (8, 3)]
    assert summarize(tasks)["next_id"] == 3


def test_current_week_uses_account_zone_at_midnight(client, monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 22, 22, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr("app.routers.week_plan.datetime", Frozen)
    assert client.patch("/me/settings", headers=auth(1), json={"timezone": "Europe/Moscow"}).status_code == 200
    for user, expected in ((1, "2026-11-23"), (2, "2026-11-16")):
        assert client.get(PLAN, headers=auth(user)).json()["week"] == expected
