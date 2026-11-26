from app.models import StudyGoalMaterial
from sqlalchemy import func, select

from tests.helpers import auth_headers as auth

GOALS = "/mobile/learning/goals"
PLAN = "/mobile/plan"
TODAY = "/mobile/learning/today"


def goal(client, name, result=None, who=1):
    response = client.post(GOALS, headers=auth(who), json={"name": name, "result": result})
    assert response.status_code == 200, response.text
    return response.json()


def content(client, title, status="unseen", who=1):
    response = client.post("/contents", headers=auth(who), json={"title": title, "note": "Synthetic"})
    assert response.status_code == 201, response.text
    material_id = response.json()["id"]
    if status != "unseen":
        response = client.patch(f"/contents/{material_id}", headers=auth(who), json={"status": status})
        assert response.status_code == 200, response.text
    return material_id


def link(client, goal_id, content_id, who=1):
    return client.post(f"{GOALS}/{goal_id}/materials", headers=auth(who), json={"content_id": content_id})


def update(client, entry, **changes):
    data = {key: entry[key] for key in ("name", "result", "status")}
    return client.put(f"{GOALS}/{entry['id']}", headers=auth(1) | {"If-Match": f'"{entry["version"]}"'},
                      json=data | changes)


def test_goal_lifecycle_and_pagination(client):
    assert client.get(GOALS).status_code == 401
    first = goal(client, "Python", "Write a program")
    second = goal(client, "SQL")
    assert goal(client, "PYTHON", "Write a program") == first
    assert client.post(GOALS, headers=auth(1), json={"name": "Python", "result": "Other"}).status_code == 409
    assert client.get(f"{GOALS}?status=active&limit=1&offset=1", headers=auth(1)).json() == {"items": [second], "total": 2}
    renamed = update(client, first, name="Python project").json()
    assert renamed["version"] == 2
    assert update(client, first, result="Stale").status_code == 412
    assert update(client, renamed, name="sql").status_code == 409
    completed = update(client, renamed, status="completed").json()
    assert completed["materials_total"] == 0 and completed["status"] == "completed"
    archived = update(client, completed, status="archived").json()
    assert client.get(f"{GOALS}?status=archived", headers=auth(1)).json()["items"] == [archived]
    assert client.delete(f"{PLAN}/goals/{first['id']}", headers=auth(1)).status_code == 409
    assert update(client, archived, status="active").json()["status"] == "active"


def test_owner_isolation_membership_and_current_progress(client, session):
    first, second, stranger = (goal(client, "First"), goal(client, "Second"), goal(client, "Foreign", who=2))
    studied = content(client, "Studied", "studied")
    irrelevant = content(client, "Irrelevant", "irrelevant")
    unseen = content(client, "Unseen")
    foreign = content(client, "Foreign material", who=2)
    for entry, material in ((first, studied), (first, studied), (second, studied), (first, irrelevant), (first, unseen)):
        assert link(client, entry["id"], material).status_code == 204
    assert session.scalar(select(func.count()).select_from(StudyGoalMaterial)) == 4
    endpoint = f"{GOALS}/{first['id']}"
    assert client.get(endpoint, headers=auth(2)).status_code == 404
    assert client.get(f"{endpoint}/materials", headers=auth(2)).status_code == 404
    assert link(client, stranger["id"], studied).status_code == 404
    assert link(client, first["id"], foreign).status_code == 404
    assert client.delete(f"{endpoint}/materials/{foreign}", headers=auth(1)).status_code == 404
    assert client.get(f"{GOALS}?content_id={foreign}", headers=auth(1)).status_code == 404
    assert client.get(f"{GOALS}?content_id={studied}", headers=auth(1)).json()["items"][1]["linked"] is True

    detail = client.get(endpoint, headers=auth(1)).json()
    assert (detail["materials_studied"], detail["materials_total"]) == (1, 2)
    assert client.get(f"{endpoint}/materials?limit=1&offset=1", headers=auth(1)).json()["total"] == 3
    assert client.delete(f"/contents/{unseen}", headers=auth(1)).status_code == 204
    assert client.get(endpoint, headers=auth(1)).json()["materials_total"] == 1
    assert client.get(TODAY, headers=auth(1)).json()["weekly_progress"]["weekly_completed"] == 1
    assert client.delete(f"{endpoint}/materials/{studied}", headers=auth(1)).status_code == 204
    assert client.get(endpoint, headers=auth(1)).json()["materials_total"] == 0
    assert client.get(f"{GOALS}/{second['id']}", headers=auth(1)).json()["materials_studied"] == 1
    assert client.get(f"/contents/{studied}", headers=auth(1)).status_code == 200


def test_goal_reuses_week_plan_and_export_remains_importable(client):
    first = goal(client, "Long study", "A result")
    material = content(client, "A material")
    day = client.get(TODAY, headers=auth(1)).json()["local_date"]
    response = client.post(PLAN + "/tasks", headers=auth(1), json={
        "goal_id": first["id"], "content_id": material, "day": day, "minutes": 15, "priority": 1,
    })
    assert response.status_code == 200, response.text
    task = response.json()
    assert client.get(PLAN, headers=auth(1)).json()["tasks"][0]["goal_id"] == first["id"]
    assert client.get(TODAY, headers=auth(1)).json()["next_action"]["task_id"] == task["id"]
    assert client.get(f"{GOALS}/{first['id']}/materials", headers=auth(1)).json()["total"] == 1
    assert update(client, first, status="archived").status_code == 200
    assert client.get(PLAN, headers=auth(1)).json()["tasks"][0]["id"] == task["id"]

    export = client.get("/me/export", headers=auth(1))
    plan = export.json()["study_plan"]
    assert plan["goals"][0]["result"] == "A result"
    assert plan["goals"][0]["status"] == "archived"
    assert plan["goal_materials"] == [{"goal_id": first["id"], "content_id": material}]
    assert plan["history"][0]["task_id"] == task["id"]
    preview = client.post("/mobile/library/imports/preview", headers=auth(2) | {"Content-Type": "application/json"},
                          content=export.content)
    assert preview.status_code == 200, preview.text
    assert client.delete(f"{GOALS}/{first['id']}/materials/{material}", headers=auth(1)).status_code == 204
    assert client.get(PLAN, headers=auth(1)).json()["tasks"][0]["id"] == task["id"]
