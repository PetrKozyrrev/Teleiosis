from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.duration import estimated_minutes, estimated_minutes_sql
from app.models import Content, StudyGoal, StudyGoalMaterial
from app.routers import time_budget
from tests.test_learning_today import goal_for, material, owner, task

PATH = "/mobile/learning/time-budget"
NOW = datetime(2026, 11, 22, 22, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def freeze_local_day(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)

    monkeypatch.setattr(time_budget, "datetime", Frozen)


def video(session, user, title, seconds, **fields):
    return material(session, user, title, content_type="video", video_duration_seconds=seconds, **fields)


def get(client, headers, budget, limit=3):
    response = client.get(PATH, params={"budget_minutes": budget, "limit": limit}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_presets_bounds_limit_and_unknown(client, session):
    assert client.get(PATH, params={"budget_minutes": 5}).status_code == 401
    user, headers = owner(session)
    for params in ({}, {"budget_minutes": 6}, {"budget_minutes": 5, "limit": 0}, {"budget_minutes": 5, "limit": 4}):
        assert client.get(PATH, params=params, headers=headers).status_code == 422
    for seconds in (1, 300, 301, 900, 901, 1800, 1801, 3600, 3601):
        video(session, user, str(seconds), seconds)
    video(session, user, "zero", 0)
    video(session, user, "unknown", None, text_character_count=55)
    video(session, user, "irrelevant", 300, status="irrelevant")
    video(session, user, "studied", 300, status="studied")
    for preset, expected in [
        (5, [5, 1]), (15, [15, 6, 5]), (30, [30, 16, 15]), (60, [60, 31, 30]),
    ]:
        result = get(client, headers, preset)
        assert result["budget_minutes"] == preset and result["local_date"] == "2026-11-23"
        assert [r["duration_minutes"] for r in result["items"]] == expected
        assert result["has_unknown_duration"] is True
    assert len(get(client, headers, 60, limit=1)["items"]) == 1


def test_ranking_deduplication_and_future_or_foreign_exclusion(client, session):
    user, headers = owner(session)
    foreign, foreign_headers = owner(session, "foreign@example.com", "UTC")
    first = goal_for(session, user)
    second = StudyGoal(user_id=user.id, name="Another goal")
    archived = StudyGoal(user_id=user.id, name="Archived", status="archived")
    session.add_all([second, archived])
    session.flush()
    urgent = video(session, user, "Urgent", 61)
    goal_item = video(session, user, "Goal", 121)
    ordinary = video(session, user, "Ordinary", 300)
    reserved = video(session, user, "Future", 300)
    too_long = video(session, user, "Long despite task estimate", 301)
    video(session, foreign, "Foreign", 300)
    for goal, item in [(first, goal_item), (second, goal_item), (archived, ordinary)]:
        session.add(StudyGoalMaterial(goal_id=goal.id, content_id=item.id, user_id=user.id))
    earliest = task(session, first, urgent, "2026-11-22")
    task(session, second, urgent, "2026-11-24")
    task(session, first, reserved, "2026-11-24")
    task(session, first, too_long, "2026-11-23")
    rows = get(client, headers, 5)["items"]
    assert [row["material_id"] for row in rows] == [urgent.id, goal_item.id, ordinary.id]
    assert (rows[0]["reason"], rows[0]["task_id"], rows[0]["task_day"]) == ("overdue_task", earliest.id, "2026-11-22")
    assert (rows[1]["reason"], rows[1]["goal_name"]) == ("active_goal", first.name)
    assert rows[2]["reason"] == "fits_time" and rows[2]["goal_name"] is None
    assert get(client, foreign_headers, 5)["local_date"] == "2026-11-22"
    assert [row["title"] for row in get(client, foreign_headers, 5)["items"]] == ["Foreign"]
    assert client.delete(f"/contents/{urgent.id}", headers=headers).status_code == 204
    assert [row["material_id"] for row in get(client, headers, 5)["items"]] == [goal_item.id, ordinary.id]


def test_stable_age_and_id_tiebreak_and_duration_contract(session, client):
    user, headers = owner(session)
    recent = datetime(2026, 11, 20, tzinfo=timezone.utc)
    older = datetime(2026, 11, 19, tzinfo=timezone.utc)
    latest = material(session, user, "Latest", note="x" * 1001, created_at=recent)
    first = material(session, user, "First", note="\u2000" + "a" * 999 + "\u00a0\u202f" + "b" + "\x1e", created_at=older)
    second = material(session, user, "Second", note="Пр" * 501, created_at=older)
    unknown = material(session, user, "Unknown", note="\n\u2001\t")
    material(session, user, "Text", note=None, url="https://example.com/article", text_character_count=1000, content_type="article")
    material(session, user, "PDF", content_type="pdf")
    for entry, sql_minutes in session.execute(select(Content, estimated_minutes_sql())):
        assert sql_minutes == estimated_minutes(entry), entry.title
    result = get(client, headers, 5)
    assert [row["material_id"] for row in result["items"]] == [first.id, second.id, latest.id]
    assert result["has_unknown_duration"] is True
    assert unknown.id not in [row["material_id"] for row in result["items"]]


def test_empty_suggestions_do_not_substitute_unknown_duration(client, session):
    user, headers = owner(session)
    assert get(client, headers, 5)["items"] == []
    assert get(client, headers, 5)["has_unknown_duration"] is False
    video(session, user, "Unknown", None)
    result = get(client, headers, 5)
    assert result["items"] == [] and result["has_unknown_duration"] is True
