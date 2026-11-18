from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.deps import get_db
from app.main import create_app
from app.models import User
from app.sessions import create_session
from tests.helpers import auth_headers


def keyed(user, key=None):
    return {**auth_headers(user), "Idempotency-Key": str(key or uuid4())}


def test_replay_survives_material_deletion_and_rejects_changed_payload(client):
    headers = keyed(1)
    payload = {"note": "A synthetic note"}
    first = client.post("/contents/submissions", json=payload, headers=headers)
    assert first.status_code == 201
    material = first.json()
    assert client.post("/contents/submissions", json=payload, headers=headers).json()["id"] == material["id"]
    assert client.post("/contents/submissions", json={"note": "Different"}, headers=headers).status_code == 409
    assert client.get("/contents", headers=headers).json()["total"] == 1
    assert client.delete(f"/contents/{material['id']}", headers=headers).status_code == 204
    assert client.post("/contents/submissions", json=payload, headers=headers).status_code == 410
    assert client.get("/contents", headers=headers).json()["total"] == 0

    other = keyed(2, headers["Idempotency-Key"])
    second = client.post("/contents/submissions", json=payload, headers=other)
    assert second.status_code == 201
    assert second.json()["id"] != material["id"]


def test_url_duplicate_receipt_and_invalid_requests(client):
    headers = keyed(1)
    url = "https://example.com/sample.pdf"
    assert client.post("/contents/submissions", json={"url": url}, headers=auth_headers(1)).status_code == 422
    assert client.post("/contents/submissions", json={}, headers=headers).status_code == 422
    first = client.post("/contents/submissions", json={"url": url}, headers=headers)
    assert first.status_code == 201
    other_key = keyed(1)
    payload = {"url": url + "#page=2"}
    second = client.post("/contents/submissions", json=payload, headers=other_key)
    assert second.status_code == 409
    assert second.json()["detail"]["existing_id"] == first.json()["id"]
    assert client.delete(f"/contents/{first.json()['id']}", headers=headers).status_code == 204
    assert client.post("/contents/submissions", json=payload, headers=other_key).status_code == 410


def test_two_simultaneous_retries_create_one_note(engine):
    with Session(engine) as session:
        owner = User(email=f"parallel-{uuid4().hex}@example.com")
        session.add(owner)
        session.flush()
        token, _ = create_session(session, owner, client_type="mobile")
        owner_id = owner.id
        session.commit()

    application = create_app()

    def database():
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_db] = database
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid4())}
    start = Barrier(2, timeout=5)

    def send():
        with TestClient(application) as client:
            start.wait()
            return client.post("/contents/submissions", json={"note": "Same note"}, headers=headers)

    try:
        with ThreadPoolExecutor(2) as threads:
            first, second = list(threads.map(lambda _: send(), range(2)))
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        with TestClient(application) as client:
            assert client.get("/contents", headers=headers).json()["total"] == 1
    finally:
        with Session(engine) as session:
            session.execute(delete(User).where(User.id == owner_id))
            session.commit()


def test_versioned_patch_detects_web_edits_and_category_removal(client):
    headers = auth_headers(1)
    category = client.post("/categories", json={"name": "One"}, headers=headers).json()
    material = client.post("/contents", headers=headers, json={
        "url": "https://example.com/example", "category_id": category["id"],
    }).json()
    path = f"/contents/{material['id']}"
    assert material["version"] == 1
    assert client.post(path + "/open", headers=headers).status_code == 204
    assert client.get(path, headers=headers).json()["version"] == 1

    edited = client.patch(path, json={"title": "Web title"}, headers=headers).json()
    assert edited["version"] == 2
    stale = client.patch(path + "/versioned", json={"title": "Stale title"}, headers={**headers, "If-Match": '"1"'})
    assert stale.status_code == 412
    assert client.get(path, headers=headers).json()["title"] == "Web title"
    assert client.patch(path + "/versioned", json={"title": "No version"}, headers=headers).status_code == 422
    assert client.patch(path + "/versioned", json={"title": "Other user"}, headers={**auth_headers(2), "If-Match": '"2"'}).status_code == 404

    assert client.delete(f"/categories/{category['id']}", headers=headers).status_code == 204
    assert client.get(path, headers=headers).json()["version"] == 3
    assert client.patch(path + "/versioned", json={"title": "Category changed"}, headers={**headers, "If-Match": '"2"'}).status_code == 412
    updated = client.patch(path + "/versioned", json={"title": "Mobile title"}, headers={**headers, "If-Match": '"3"'})
    assert updated.status_code == 200
    assert updated.json()["version"] == 4
