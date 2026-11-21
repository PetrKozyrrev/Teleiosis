import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.library_import import FILE_LIMIT
from app.models import Content, ContentGroup, LibraryGroup, LibraryImport, User
from app.routers.library_import import run_import
from tests.helpers import auth_headers

IMPORT = "/mobile/library/imports"
SEARCH = "/mobile/library/search"


def export(**fields):
    return {"version": 1, "categories": [], "contents": [], **fields}


def test_export_roundtrip_maps_ids_to_current_account_and_never_overwrites(client, monkeypatch):
    source, target = auth_headers(1), auth_headers(2)
    category = client.post("/categories", headers=source, json={"name": "Учёба"}).json()
    own_category = client.post("/categories", headers=target, json={"name": "учёба"}).json()
    existing = client.post("/contents", headers=target, json={
        "url": "https://example.com/kept?utm_source=app", "title": "Существующий",
    }).json()
    duplicate = client.post("/contents", headers=source, json={
        "url": "https://www.example.com/kept#read", "title": "Дубль",
    }).json()
    note = client.post("/contents", headers=source, json={
        "title": "Название", "note": "Текст", "category_id": category["id"],
    }).json()
    note = client.patch(f"/contents/{note['id']}", headers=source, json={"status": "studied"}).json()
    client.post(f"/contents/{note['id']}/open", headers=source)
    tag = client.post("/tags", headers=source, json={"name": "Метка"}).json()
    reused_tag = client.post("/tags", headers=target, json={"name": "метка"}).json()
    collection = client.post("/collections", headers=source, json={"name": "Подборка"}).json()
    client.post("/tags", headers=source, json={"name": "Пустой тег"})
    for row in (note, duplicate):
        response = client.patch(f"/contents/{row['id']}/organization",
            headers={**source, "If-Match": f'"{row["version"]}"'},
            json={"tag_ids": [tag["id"]], "collection_ids": [collection["id"]]})
        assert response.status_code == 200, response.text

    def forbid_fetch(*_args):
        pytest.fail("Import must not fetch external metadata")
    monkeypatch.setattr("app.routers.contents.fetch_metadata", forbid_fetch)
    file = client.get("/me/export", headers=source).json()
    file["contents"][0]["user_id"] = file["user"]["id"]
    expected = {"materials": 1, "duplicates": 1, "categories": 0, "tags": 1,
                "collections": 1, "memberships": 2, "replayed": False}
    preview = client.post(f"{IMPORT}/preview", headers=target, json=file)
    assert preview.status_code == 200, preview.text
    assert preview.json() == expected
    assert client.get("/contents", headers=target).json()["items"] == [existing]
    assert client.get("/collections", headers=target).json() == []
    assert client.post(f"{IMPORT}/apply", headers=target, json=file).json() == expected

    imported = next(item for item in client.get("/contents", headers=target).json()["items"] if item["note"] == "Текст")
    assert imported["id"] != note["id"]
    assert imported["category_id"] == own_category["id"]
    assert (imported["status"], imported["studied_at"], imported["open_count"], imported["version"]) == (
        "studied", note["studied_at"], 1, 1,
    )
    organization = client.get(f"/contents/{imported['id']}/organization", headers=target).json()
    assert organization["tags"] == [{"id": reused_tag["id"], "name": "метка"}]
    assert organization["collections"][0]["id"] != collection["id"]
    assert organization["collections"][0]["name"] == "Подборка"
    assert client.get(f"/contents/{existing['id']}", headers=target).json() == existing
    assert client.get(f"/contents/{existing['id']}/organization", headers=target).json()["tags"] == []
    assert client.get(f"/contents/{imported['id']}", headers=source).status_code == 404
    assert client.post(f"{IMPORT}/preview", headers=source, json=file).json()["replayed"] is False

    # The exact retry returns its receipt even after intentional edits or deletion.
    client.delete(f"/contents/{imported['id']}", headers=target)
    for mode in ("preview", "apply"):
        assert client.post(f"{IMPORT}/{mode}", headers=target, json=file).json() == {**expected, "replayed": True}
    assert client.get("/contents", headers=target).json()["items"] == [existing]


def test_legacy_export_and_dedup_within_file_and_across_serializations(client):
    headers = auth_headers(1)
    note = {"id": 2, "title": "Совпадение", "note": "Текст"}
    link = {"id": 4, "title": "Ссылка", "url": "https://example.com/page?utm_source=test"}
    data = export(contents=[note, {**note, "id": 3}, link, {**link, "id": 5, "url": "http://www.example.com/page/#anchor"}])
    first = client.post(f"{IMPORT}/apply", headers=headers, json=data).json()
    assert first["materials"] == 2 and first["duplicates"] == 2
    second = client.post(f"{IMPORT}/apply", headers={**headers, "Content-Type": "application/json"},
                         content=json.dumps(data, ensure_ascii=False, indent=2).encode()).json()
    assert not second["replayed"] and second["materials"] == 0 and second["duplicates"] == 4


@pytest.mark.parametrize(("data", "code", "location"), [
    ({"version": True}, "unsupported_export_version", ["version"]),
    (export(contents=[{"id": 1, "title": "Пример"}]), "missing_material_content", ["contents", 0]),
    (export(contents=[{"id": 1, "title": "Пример", "note": "текст", "category_id": 7}]),
     "unknown_reference", ["contents", 0, "category_id"]),
    (export(categories=[{"id": 1, "name": "A"}, {"id": 1, "name": "B"}]), "repeated_id", ["categories", 1, "id"]),
    (export(organization=[{"content_id": 1, "group_id": 2}]), "unknown_reference", ["organization", 0]),
    (export(tags=[{"id": 1, "name": "A"}], collections=[{"id": 1, "name": "B"}]), "repeated_id", ["collections"]),
    (export(contents=[{"id": 1, "title": "Пример", "url": "file:///somewhere"}]), "invalid_export_field", ["contents", 0, "url"]),
    (export(contents=[{"id": 1, "title": "Пример", "note": "x" * 10_001}]), "invalid_export_field", ["contents", 0, "note"]),
    (export(contents=[{"id": 1, "title": "Пример", "note": "Текст", "created_at": 1}]),
     "invalid_export_field", ["contents", 0, "created_at"]),
    (export(contents=[{}] * 501), "invalid_export_field", ["contents"]),
    (export(tags=[{}] * 201), "invalid_export_field", ["tags"]),
    (export(categories=[{}] * 201), "invalid_export_field", ["categories"]),
])
def test_invalid_export_is_atomic_and_reports_safe_location(client, data, code, location):
    headers = auth_headers(1)
    for mode in ("preview", "apply"):
        response = client.post(f"{IMPORT}/{mode}", headers=headers, json=data)
        assert response.status_code == 422
        assert response.json()["detail"] == {"code": code, "location": location}
    assert client.get("/contents", headers=headers).json()["total"] == 0
    assert client.get("/categories", headers=headers).json() == []


@pytest.mark.parametrize("raw", [b"broken", b'{"version": 1, "version": 1}', b'{"version": 1, "user": "\xff"}'])
def test_import_rejects_malformed_json(client, raw):
    response = client.post(f"{IMPORT}/apply", headers={**auth_headers(1), "Content-Type": "application/json"}, content=raw)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_json"


def test_limits_auth_csrf_and_membership_quota(client, session):
    headers = auth_headers(1)
    assert client.post(f"{IMPORT}/preview", json=export()).status_code == 401
    assert client.post(f"{IMPORT}/apply", headers={**headers, "Origin": "https://foreign.example"}, json=export()).status_code == 403
    assert client.post(f"{IMPORT}/preview", headers=headers, content="{}").status_code == 415
    oversized = client.post(f"{IMPORT}/preview", headers={**headers, "Content-Type": "application/json"},
                            content=(b" " * 100_000 for _ in range(FILE_LIMIT // 100_000 + 1)))
    assert oversized.status_code == 413
    owner = session.scalar(select(User.id).where(User.email == "user1@example.com"))
    session.add_all(LibraryGroup(user_id=owner, name=f"Метка {index}", kind="tag") for index in range(200))
    session.flush()
    file = export(tags=[{"id": 1, "name": "Ещё одна"}], categories=[{"id": 2, "name": "Новая"}])
    for mode in ("preview", "apply"):
        response = client.post(f"{IMPORT}/{mode}", headers=headers, json=file)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "group_limit_reached"
    assert client.get("/categories", headers=headers).json() == []
    assignments = export(contents=[{"id": 1, "title": "Заметка", "note": "Текст"}],
                         tags=[{"id": index, "name": f"Метка {index}"} for index in range(1, 22)],
                         organization=[{"content_id": 1, "group_id": index} for index in range(1, 22)])
    response = client.post(f"{IMPORT}/apply", headers=headers, json=assignments)
    assert response.status_code == 422 and response.json()["detail"]["code"] == "assignment_limit"


def test_late_failure_rolls_back_new_materials_categories_groups_and_receipt(client):
    headers = auth_headers(1)
    file = export(contents=[{"id": 1, "title": "Материал", "note": "Текст", "category_id": 2}],
                  categories=[{"id": 2, "name": "Категория"}], tags=[{"id": 3, "name": "Тег"}],
                  organization=[{"content_id": 1, "group_id": 3}])
    def fail(*_args):
        raise IntegrityError("synthetic membership failure", {}, Exception())
    event.listen(ContentGroup, "before_insert", fail)
    try:
        assert client.post(f"{IMPORT}/apply", headers=headers, json=file).status_code == 409
    finally:
        event.remove(ContentGroup, "before_insert", fail)
    assert client.get("/contents", headers=headers).json()["total"] == 0
    assert client.get("/categories", headers=headers).json() == []
    assert client.get("/tags", headers=headers).json() == []
    retried = client.post(f"{IMPORT}/apply", headers=headers, json=file).json()
    assert retried == {"materials": 1, "duplicates": 0, "categories": 1, "tags": 1,
                       "collections": 0, "memberships": 1, "replayed": False}


def test_concurrent_apply_does_not_duplicate_notes_or_receipts(engine):
    raw = json.dumps(export(contents=[{"id": 1, "title": "Parallel", "note": "Test note"}])).encode()
    with Session(engine) as db, db.begin():
        owner = User(email="parallel-import@example.com")
        db.add(owner)
        db.flush()
        user_id = owner.id

    def apply(_index):
        with Session(engine) as db:
            return run_import("apply", db, db.get(User, user_id), raw)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            receipts = list(executor.map(apply, range(2)))
        assert sorted(receipt.replayed for receipt in receipts) == [False, True]
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Content).where(Content.user_id == user_id)) == 1
            assert db.scalar(select(func.count()).select_from(LibraryImport).where(LibraryImport.user_id == user_id)) == 1
    finally:
        with Session(engine) as db, db.begin():
            db.delete(db.get(User, user_id))
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(LibraryImport).where(LibraryImport.user_id == user_id)) == 0


def test_search_fields_pagination_literal_matching_isolation_and_legacy_route(client):
    headers, other = auth_headers(1), auth_headers(2)
    doc = export(categories=[{"id": 8, "name": "Темы"}], tags=[{"id": 10, "name": "Тег"}],
                 collections=[{"id": 11, "name": "Коллекция"}], contents=[
        {"id": 1, "title": "Общее", "note": "Запись 90%_ТЕСТ", "status": "studied", "category_id": 8,
         "url": "https://example.com/first"},
        {"id": 2, "title": "Общее", "description": "90%_тест", "status": "studied", "category_id": 8,
         "url": "https://example.com/second"},
        {"id": 3, "title": "Без группы", "note": "90xxтест"},
    ], organization=[{"content_id": index, "group_id": group} for index in (1, 2) for group in (10, 11)])
    assert client.post(f"{IMPORT}/apply", headers=headers, json=doc).status_code == 200
    category = client.get("/categories", headers=headers).json()[0]["id"]
    tag = client.get("/tags", headers=headers).json()[0]["id"]
    collection = client.get("/collections", headers=headers).json()[0]["id"]
    filt = {"q": "90%_тест", "status": "studied", "source": "web", "category_id": category, "tag_id": tag,
            "collection_id": collection, "sort": "title", "limit": 1}
    first = client.get(SEARCH, headers=headers, params=filt).json()
    second = client.get(SEARCH, headers=headers, params={**filt, "offset": 1}).json()
    assert first["total"] == second["total"] == 2 and first["items"][0]["id"] < second["items"][0]["id"]
    assert client.get(SEARCH, headers=other, params=filt).json()["total"] == 0
    for scope, term, count in (("all", "90%_тест", 2), ("note", "90%_ТЕСТ", 1), ("url", "second", 1),
                               ("title", "общ", 2), ("description", "90%_тест", 1)):
        assert client.get(SEARCH, headers=headers, params={"search_in": scope, "q": term}).json()["total"] == count
    assert client.get("/contents", headers=headers, params={"q": "90%_тест", "search_in": "all"}).json()["total"] == 0
    assert client.get(SEARCH, headers=headers, params={"search_in": "invalid"}).status_code == 422
    assert client.get(SEARCH, headers=headers, params={"q": "x" * 101}).status_code == 422
    registered = client.post("/mobile/auth/register", json={
        "email": "mobile-search@example.com", "password": "synthetic-password", "consent": True,
    })
    assert registered.status_code == 201
    bearer = {"Authorization": "Bearer " + registered.json()["token"]}
    assert client.post(f"{IMPORT}/apply", headers=bearer, json=doc).status_code == 200
    assert client.get(SEARCH, headers=bearer, params={"q": "90%_тест"}).json()["total"] == 2
    assert client.post("/mobile/auth/logout", headers=bearer, json={}).status_code == 204
    assert client.get(SEARCH, headers=bearer).status_code == 401
    assert client.post(f"{IMPORT}/apply", headers=bearer, json=doc).status_code == 401
