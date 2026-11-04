def auth(telegram_id):
    return {"X-Dev-Telegram-Id": str(telegram_id)}


def create(client, name, telegram_id=1):
    return client.post("/categories", json={"name": name}, headers=auth(telegram_id))


def test_requires_auth(client):
    assert client.get("/categories").status_code == 401


def test_create_and_list(client):
    response = create(client, "Бизнес")
    assert response.status_code == 201
    assert response.json()["name"] == "Бизнес"

    response = client.get("/categories", headers=auth(1))
    assert [c["name"] for c in response.json()] == ["Бизнес"]


def test_name_is_trimmed(client):
    assert create(client, "  Финансы  ").json()["name"] == "Финансы"


def test_invalid_names_rejected(client):
    assert create(client, "").status_code == 422
    assert create(client, "   ").status_code == 422
    assert create(client, "x" * 51).status_code == 422


def test_duplicate_name_conflict(client):
    assert create(client, "Бизнес").status_code == 201
    assert create(client, "Бизнес").status_code == 409


def test_same_name_for_different_users_allowed(client):
    assert create(client, "Бизнес", telegram_id=1).status_code == 201
    assert create(client, "Бизнес", telegram_id=2).status_code == 201


def test_rename(client):
    category_id = create(client, "Старое").json()["id"]
    response = client.patch(
        f"/categories/{category_id}", json={"name": "Новое"}, headers=auth(1)
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Новое"


def test_rename_to_existing_name_conflict(client):
    create(client, "A")
    b_id = create(client, "B").json()["id"]
    response = client.patch(
        f"/categories/{b_id}", json={"name": "A"}, headers=auth(1)
    )
    assert response.status_code == 409


def test_delete(client):
    category_id = create(client, "Удалить").json()["id"]
    assert client.delete(f"/categories/{category_id}", headers=auth(1)).status_code == 204
    assert client.get("/categories", headers=auth(1)).json() == []
    assert client.delete(f"/categories/{category_id}", headers=auth(1)).status_code == 404


def test_other_user_cannot_see_or_change_category(client):
    category_id = create(client, "Секрет", telegram_id=1).json()["id"]

    # Пользователь 2 не видит чужую категорию в списке
    assert client.get("/categories", headers=auth(2)).json() == []

    # и не может ни переименовать, ни удалить её (404, а не 403)
    response = client.patch(
        f"/categories/{category_id}", json={"name": "Взлом"}, headers=auth(2)
    )
    assert response.status_code == 404
    assert client.delete(f"/categories/{category_id}", headers=auth(2)).status_code == 404

    # у владельца всё осталось как было
    names = [c["name"] for c in client.get("/categories", headers=auth(1)).json()]
    assert names == ["Секрет"]