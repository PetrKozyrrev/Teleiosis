from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select

from app.models import LearningCompletion, StudyTaskEvent
from app.sessions import create_session
from app.models import User
from tests.helpers import auth_headers as auth

PLAN = "/mobile/plan"
ROOT = "/mobile/learning/materials"


def material(client, who=1):
    response = client.post("/contents", headers=auth(who), json={"note": "Original, preserved note"})
    assert response.status_code == 201
    return response.json()


def schedule(client, entry, name, who=1):
    goal = client.post(PLAN + "/goals", headers=auth(who), json={"name": name}).json()
    day = client.get("/mobile/learning/today", headers=auth(who)).json()["local_date"]
    response = client.post(PLAN + "/tasks", headers=auth(who), json={
        "goal_id": goal["id"], "content_id": entry["id"], "day": day, "minutes": 15, "priority": 2,
    })
    assert response.status_code == 200
    return response.json()


def complete(client, entry, *, task=None, key=None, headers=None):
    return client.post(f"{ROOT}/{entry['id']}/completion",
                       headers=(headers or auth(1)) | {"Idempotency-Key": str(key or uuid4()), "If-Match": f'"{entry["version"]}"'},
                       json={"task_id": task})


def test_completion_from_library_leaves_tasks_and_reuses_review(client):
    entry = material(client)
    task = schedule(client, entry, "Goal")
    path = f"{ROOT}/{entry['id']}"
    options = client.get(path + "/completion", headers=auth(1)).json()
    assert options["material"]["status"] == "unseen" and [t["id"] for t in options["tasks"]] == [task["id"]]
    assert options["reflection"] is None
    result = complete(client, entry).json()
    assert result["material"]["status"] == "studied" and result["task_completed"] is False
    assert result["material"]["note"] == entry["note"]
    assert client.get(PLAN, headers=auth(1)).json()["tasks"][0]["completed_at"] is None
    response = client.put(path + "/reflection", headers=auth(1), json={"thought": "My takeaway", "previous": None})
    assert response.status_code == 200
    reflection = response.json()
    assert client.put(path + "/reflection", headers=auth(1), json={"thought": "My takeaway", "previous": None}).json() == reflection
    assert client.put(path + "/reflection", headers=auth(1), json={"thought": "Other", "previous": None}).status_code == 412
    assert client.get(path + "/completion", headers=auth(1)).json()["reflection"] == reflection
    assert client.get("/me/export", headers=auth(1)).json()["reflections"] == [
        {"content_id": entry["id"], "thought": "My takeaway"},
    ]

    card = client.post("/mobile/review", headers=auth(1) | {"Idempotency-Key": str(uuid4())},
                       json={"content_id": entry["id"], "question": "Q?", "answer": "A."})
    assert card.status_code == 200
    assert client.get("/mobile/review", headers=auth(1)).json()["total"] == 1
    undone = client.patch(f"/contents/{entry['id']}", headers=auth(1), json={"status": "planned"}).json()
    assert undone["studied_at"] is None
    assert client.get(path + "/completion", headers=auth(1)).json()["reflection"] == reflection
    assert client.get("/mobile/review", headers=auth(1)).json()["total"] == 1


def test_atomic_task_completion_replay_and_undo(client, session):
    entry = material(client)
    first, second = schedule(client, entry, "First"), schedule(client, entry, "Second")
    other_material = material(client)
    unrelated = schedule(client, other_material, "Third")
    owner = session.scalar(select(User).where(User.email == "user1@example.com"))
    token, _ = create_session(session, owner, client_type="mobile")
    headers = {"Authorization": f"Bearer {token}"}
    key = uuid4()
    assert complete(client, entry, task=unrelated["id"], headers=headers).status_code == 404
    assert session.scalar(select(func.count()).select_from(LearningCompletion)) == 0
    assert client.get(f"/contents/{entry['id']}", headers=headers).json()["status"] == "unseen"

    first_response = complete(client, entry, task=first["id"], key=key, headers=headers)
    assert first_response.status_code == 200, first_response.text
    assert first_response.headers["cache-control"] == "no-store"
    result = first_response.json()
    assert result["task_completed"] is True
    assert result == complete(client, entry, task=first["id"], key=key, headers=headers).json()
    assert complete(client, entry, task=second["id"], key=key, headers=headers).status_code == 409
    assert complete(client, entry, task=second["id"], headers=headers).status_code == 412
    week = {task["id"]: task for task in client.get(PLAN, headers=headers).json()["tasks"]}
    assert datetime.fromisoformat(week[first["id"]]["completed_at"]) == datetime.fromisoformat(result["material"]["studied_at"])
    assert week[second["id"]]["completed_at"] is None
    assert session.scalar(select(func.count()).select_from(StudyTaskEvent).where(StudyTaskEvent.kind == "completed")) == 1
    today = client.get("/mobile/learning/today", headers=headers).json()
    assert today["weekly_progress"]["tasks_done"] == today["weekly_progress"]["weekly_completed"] == 1

    client.patch(f"/contents/{entry['id']}", headers=headers, json={"status": "planned"})
    replay = complete(client, entry, task=first["id"], key=key, headers=headers).json()
    assert replay["material"]["status"] == "planned" and replay["material"]["studied_at"] is None
    assert replay["task_completed"] is True
    assert session.scalar(select(func.count()).select_from(StudyTaskEvent).where(StudyTaskEvent.kind == "completed")) == 1


def test_cross_account_completion_and_reflection(client):
    entry = material(client)
    foreign = material(client, 2)
    foreign_task = schedule(client, foreign, "Foreign", 2)
    path = f"{ROOT}/{entry['id']}"
    assert client.get(path + "/completion").status_code == 401
    assert client.get(path + "/completion", headers=auth(2)).status_code == 404
    assert complete(client, entry, task=foreign_task["id"]).status_code == 404
    assert complete(client, entry, headers=auth(2)).status_code == 404
    assert client.put(path + "/reflection", headers=auth(2), json={"thought": "Forbidden", "previous": None}).status_code == 404
    assert client.get(path + "/completion", headers=auth(1)).json()["material"]["status"] == "unseen"
