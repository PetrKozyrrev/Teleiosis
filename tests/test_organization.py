from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.main import create_app
from app.sessions import create_session
from sqlalchemy.exc import IntegrityError

from app.models import Content, ContentGroup, LibraryGroup, User
from tests.helpers import ORIGIN, auth_headers as auth


def group(client, name="Метка", resource="tags", user=1):
    response = client.post(f"/{resource}", json={"name": name}, headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()


def material(client, user=1, **data):
    response = client.post("/contents", json={"note": "Synthetic note", **data}, headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()


def assign(client, item, user=1, **body):
    return client.patch(f"/contents/{item['id']}/organization", json=body,
                        headers={**auth(user), "If-Match": f'"{item["version"]}"'})


@pytest.mark.parametrize("resource", ["tags", "collections"])
def test_group_lifecycle_and_isolation(client, resource):
    a = group(client, "  Тест  ", resource)
    b = group(client, "Тест", resource, user=2)
    assert a["name"] == "Тест" and a["contents_count"] == 0
    assert client.post(f"/{resource}", headers=auth(1), json={"name": "тест"}).status_code == 409
    assert [row["id"] for row in client.get(f"/{resource}", headers=auth(1)).json()] == [a["id"]]
    path = f"/{resource}/{a['id']}"
    assert client.patch(path, headers=auth(2), json={"name": "stolen"}).status_code == 404
    assert client.delete(path, headers=auth(2)).status_code == 404
    assert client.patch(path, headers=auth(1), json={"name": "Новое"}).json()["name"] == "Новое"
    assert client.delete(path, headers=auth(1)).status_code == 204
    assert client.delete(path, headers=auth(1)).status_code == 404
    assert client.get(f"/{resource}", headers=auth(2)).json()[0]["id"] == b["id"]


@pytest.mark.parametrize("name", ["", "  ", "x" * 51, None, 1])
def test_group_names_validation(client, name):
    assert client.post("/tags", headers=auth(1), json={"name": name}).status_code == 422


def test_kind_and_owner_quotas(client, monkeypatch):
    monkeypatch.setattr("app.routers.organization.GROUP_LIMIT", 1)
    tag = group(client)
    assert client.post("/tags", headers=auth(1), json={"name": "second"}).status_code == 409
    group(client, resource="collections")
    group(client, user=2)
    assert client.delete(f"/collections/{tag['id']}", headers=auth(1)).status_code == 404
    assert client.post("/tags", headers=auth(1), json={"name": "other", "user_id": 2}).status_code == 422


def test_assign_versions_counts_filters_and_web_compatibility(client):
    tag, tag2 = group(client), group(client, "Другое")
    collection = group(client, "Подборка", "collections")
    first, second, third = [material(client, title=f"Item {i}") for i in range(3)]
    response = assign(client, first, tag_ids=[tag["id"], tag2["id"]], collection_ids=[collection["id"]])
    assert response.status_code == 200, response.text
    assigned = response.json()
    assert assigned["version"] == first["version"] + 1
    assert len(assigned["tags"]) == 2 and len(assigned["collections"]) == 1
    assert assign(client, first, tag_ids=[]).status_code == 412
    assert client.patch(f"/contents/{first['id']}/versioned", headers={**auth(1), "If-Match": '"1"'}, json={"title": "stale"}).status_code == 412
    current = client.get(f"/contents/{first['id']}", headers=auth(1)).json()
    assert assign(client, current, tag_ids=[tag2["id"], tag["id"]]).json()["version"] == current["version"]
    assert assign(client, second, tag_ids=[tag["id"]]).status_code == 200
    params = {"tag_id": tag["id"], "collection_id": collection["id"], "q": "Item", "sort": "title", "limit": 1}
    result = client.get("/contents", headers=auth(1), params=params).json()
    assert result["total"] == 1 and result["items"][0]["id"] == first["id"]
    assert client.get("/contents", headers=auth(1), params={**params, "offset": 1}).json()["items"] == []
    assert client.get("/contents", headers=auth(1), params={"tag_id": tag["id"]}).json()["total"] == 2
    assert client.get("/contents", headers=auth(1), params={"tag_id": collection["id"]}).json()["total"] == 0
    assert client.get("/contents", headers=auth(2), params=params).json()["total"] == 0
    assert client.get("/tags", headers=auth(1)).json()[0]["contents_count"] in (1, 2)
    # Existing web PATCH remains compatible and preserves organization.
    assert client.patch(f"/contents/{first['id']}", headers=auth(1), json={"title": "Web changed"}).status_code == 200
    assert len(client.get(f"/contents/{first['id']}/organization", headers=auth(1)).json()["tags"]) == 2
    assert client.get(f"/contents/{third['id']}/organization", headers=auth(1)).json()["tags"] == []


@pytest.mark.parametrize("body", [{}, {"tag_ids": None}, {"tag_ids": [1, 1]}, {"tag_ids": [True]},
    {"tag_ids": [0]}, {"tag_ids": ["1"]}, {"collection_ids": list(range(1, 22))}, {"unknown": []}])
def test_selection_validation(client, body):
    item = material(client)
    assert assign(client, item, **body).status_code == 422


def test_assignment_is_atomic_and_requires_version_and_owner(client):
    item = material(client)
    own, foreign, collection = group(client), group(client, user=2), group(client, resource="collections")
    path = f"/contents/{item['id']}/organization"
    for ids in ([foreign["id"]], [999999], [collection["id"]]):
        assert assign(client, item, tag_ids=ids, collection_ids=[collection["id"]]).status_code == 404
        assert client.get(path, headers=auth(1)).json()["collections"] == []
    assert client.get(path, headers=auth(2)).status_code == 404
    assert assign(client, item, user=2, tag_ids=[foreign["id"]]).status_code == 404
    assert client.patch(path, headers=auth(1), json={"tag_ids": [own["id"]]}).status_code == 422
    assert client.get(path, headers=auth(1)).json()["version"] == 1


def test_delete_groups_preserves_material_and_invalidates_version(client, session):
    tag, collection = group(client), group(client, resource="collections")
    item = material(client)
    assert assign(client, item, tag_ids=[tag["id"]], collection_ids=[collection["id"]]).status_code == 200
    current = client.get(f"/contents/{item['id']}", headers=auth(1)).json()
    assert client.delete(f"/tags/{tag['id']}", headers=auth(1)).status_code == 204
    after = client.get(f"/contents/{item['id']}/organization", headers=auth(1)).json()
    assert after["version"] == current["version"] + 1
    assert after["tags"] == [] and len(after["collections"]) == 1
    assert assign(client, current, collection_ids=[]).status_code == 412
    assert client.delete(f"/contents/{item['id']}", headers=auth(1)).status_code == 204
    assert session.scalar(select(ContentGroup)) is None
    assert client.get("/collections", headers=auth(1)).json()[0]["contents_count"] == 0


def test_export_and_account_cascade(client, session):
    tag, collection = group(client), group(client, resource="collections")
    group(client, "private-other", user=2)
    item = material(client)
    assign(client, item, tag_ids=[tag["id"]], collection_ids=[collection["id"]])
    body = client.get("/me/export", headers=auth(1)).json()
    assert body["version"] == 1
    assert [t["id"] for t in body["tags"]] == [tag["id"]]
    assert [c["id"] for c in body["collections"]] == [collection["id"]]
    assert len(body["organization"]) == 2
    session.execute(delete(User).where(User.id == session.get(Content, item["id"]).user_id))
    session.flush()
    assert session.scalar(select(ContentGroup)) is None
    assert session.scalars(select(LibraryGroup)).all()[0].name == "private-other"


def test_database_rejects_cross_owner_membership(client, session):
    item = material(client)
    foreign = group(client, user=2)
    owner = session.get(Content, item["id"]).user_id
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(ContentGroup(user_id=owner, content_id=item["id"], group_id=foreign["id"]))
        session.flush()


def test_mobile_alias_bearer_cookie_csrf_and_legacy_submission(client):
    response = client.post("/mobile/auth/register", json={"email": "org-mobile@example.com", "password": "synthetic-test-password", "consent": True})
    token = {"Authorization": "Bearer " + response.json()["token"]}
    a = client.post("/mobile/library/tags", headers=token, json={"name": "Mobile"})
    assert a.status_code == 201
    submission_headers = {**token, "Idempotency-Key": str(uuid4())}
    item = client.post("/contents/submissions", headers=submission_headers, json={"note": "legacy payload"})
    assert item.status_code == 201
    path = f"/mobile/library/contents/{item.json()['id']}/organization"
    assigned = client.patch(path, headers={**token, "If-Match": '"1"'}, json={"tag_ids": [a.json()["id"]]})
    assert assigned.status_code == 200
    assert client.get(path, headers=token).json() == assigned.json()
    replay = client.post("/contents/submissions", headers=submission_headers, json={"note": "legacy payload"})
    assert replay.status_code == 201 and replay.json()["id"] == item.json()["id"]
    assert client.get("/contents", headers=token).json()["total"] == 1
    web = auth(1)
    assert client.post("/tags", headers={**web, "Origin": "https://evil.example.com"}, json={"name": "blocked"}).status_code == 403
    assert client.post("/collections", headers=web, json={"name": "Web"}).status_code == 201
    assert client.get("/mobile/library/tags", headers={**web, **token}).status_code == 401
    client.cookies.clear()
    assert client.get("/tags").status_code == 401


@pytest.mark.parametrize("operation", ["quota", "assign-delete"])
def test_concurrent_organization_writes_are_serialized_per_owner(engine, monkeypatch, operation):
    with Session(engine) as db:
        user = User(email=f"org-parallel-{uuid4().hex}@example.com")
        db.add(user)
        db.flush()
        token, _ = create_session(db, user, client_type="mobile")
        owner_id = user.id
        content = Content(user_id=owner_id, title="Synthetic race", note="Preserve")
        tag = LibraryGroup(user_id=owner_id, kind="tag", name="Existing")
        db.add_all([content, tag])
        db.flush()
        content_id, tag_id = content.id, tag.id
        db.commit()
    application = create_app()
    def database():
        with Session(engine) as db:
            yield db
    application.dependency_overrides[get_db] = database
    barrier = Barrier(2, timeout=5)
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr("app.routers.organization.GROUP_LIMIT", 2)
    def send(index):
        with TestClient(application) as client:
            barrier.wait()
            if operation == "quota":
                return client.post("/tags", headers=headers, json={"name": f"Concurrent {index}"})
            if index == 0:
                return client.patch(f"/contents/{content_id}/organization", headers={**headers, "If-Match": '"1"'}, json={"tag_ids": [tag_id]})
            return client.delete(f"/tags/{tag_id}", headers=headers)
    try:
        with ThreadPoolExecutor(2) as threads:
            results = list(threads.map(send, range(2)))
        with Session(engine) as db:
            if operation == "quota":
                assert sorted(result.status_code for result in results) == [201, 409]
                assert len(db.scalars(select(LibraryGroup).where(LibraryGroup.user_id == owner_id)).all()) == 2
            else:
                assert results[0].status_code in (200, 404)
                assert results[1].status_code == 204
                assert db.scalar(select(ContentGroup).where(ContentGroup.user_id == owner_id)) is None
                assert db.get(Content, content_id).note == "Preserve"
    finally:
        with Session(engine) as db:
            db.execute(delete(User).where(User.id == owner_id))
            db.commit()
