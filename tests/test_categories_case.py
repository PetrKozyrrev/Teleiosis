import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Category, User
from tests.helpers import auth_headers as auth


def create(client, name, telegram_id=1):
    return client.post("/categories", json={"name": name}, headers=auth(telegram_id))


def rename(client, category_id, name, telegram_id=1):
    return client.patch(
        f"/categories/{category_id}", json={"name": name}, headers=auth(telegram_id)
    )


def listing(client, telegram_id=1):
    return client.get("/categories", headers=auth(telegram_id)).json()


def save(client, telegram_id=1, **body):
    response = client.post("/contents", json=body, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()


# ---------- уникальность без учёта регистра ----------


@pytest.mark.parametrize(
    "first, second",
    [("Бизнес", "бизнес"), ("Бизнес", "БИЗНЕС"), ("Sales", "sales"), ("Бизнес", "  Бизнес ")],
)
def test_names_differing_only_by_case_conflict(client, first, second):
    assert create(client, first).status_code == 201
    assert create(client, second).status_code == 409


def test_different_names_are_fine(client):
    assert create(client, "Бизнес").status_code == 201
    assert create(client, "Бизнес 2").status_code == 201


def test_same_name_for_another_user_is_fine(client):
    assert create(client, "Бизнес", telegram_id=1).status_code == 201
    assert create(client, "бизнес", telegram_id=2).status_code == 201


def test_rename_to_name_taken_in_other_case_conflicts(client):
    create(client, "A")
    b_id = create(client, "B").json()["id"]
    assert rename(client, b_id, "a").status_code == 409
    assert [c["name"] for c in listing(client)] == ["A", "B"]


def test_rename_to_other_case_of_itself_is_allowed(client):
    category_id = create(client, "бизнес").json()["id"]
    response = rename(client, category_id, "Бизнес")
    assert response.status_code == 200
    assert response.json()["name"] == "Бизнес"


def test_database_enforces_case_insensitive_uniqueness(session):
    user = User(telegram_id=1)
    session.add(user)
    session.flush()
    session.add(Category(user_id=user.id, name="Бизнес"))
    session.flush()
    with pytest.raises(IntegrityError):
        session.add(Category(user_id=user.id, name="бизнес"))
        session.flush()


# ---------- число материалов ----------


def test_contents_count_in_list(client):
    a = create(client, "A").json()
    b = create(client, "B").json()
    assert a["contents_count"] == 0

    save(client, url="https://example.com/1", category_id=a["id"])
    save(client, url="https://example.com/2", category_id=a["id"])
    save(client, note="в B", category_id=b["id"])
    save(client, note="без категории")

    counts = {c["name"]: c["contents_count"] for c in listing(client)}
    assert counts == {"A": 2, "B": 1}


def test_count_follows_changes(client):
    category = create(client, "A").json()
    first = save(client, url="https://example.com/1", category_id=category["id"])
    save(client, url="https://example.com/2", category_id=category["id"])
    assert listing(client)[0]["contents_count"] == 2

    client.delete(f"/contents/{first['id']}", headers=auth(1))
    assert listing(client)[0]["contents_count"] == 1

    second = client.get("/contents", headers=auth(1)).json()["items"][0]
    client.patch(f"/contents/{second['id']}", json={"category_id": None}, headers=auth(1))
    assert listing(client)[0]["contents_count"] == 0


def test_rename_returns_current_count(client):
    category = create(client, "A").json()
    save(client, note="x", category_id=category["id"])
    assert rename(client, category["id"], "Новое").json()["contents_count"] == 1


def test_count_does_not_include_other_users_materials(client):
    mine = create(client, "A", telegram_id=1).json()
    theirs = create(client, "A", telegram_id=2).json()
    save(client, 2, note="чужая", category_id=theirs["id"])
    assert [c["contents_count"] for c in listing(client, 1)] == [0]
    assert mine["id"] != theirs["id"]


def test_deleting_category_keeps_materials_without_category(client):
    category = create(client, "A").json()
    item = save(client, note="x", category_id=category["id"])
    assert client.delete(f"/categories/{category['id']}", headers=auth(1)).status_code == 204
    body = client.get(f"/contents/{item['id']}", headers=auth(1)).json()
    assert body["category_id"] is None