from tests.helpers import ORIGIN


def test_library_shared_with_web_and_isolated_between_mobile_accounts(client):
    passwords = {"owner": "synthetic-owner-password", "other": "synthetic-other-password"}
    mobile = {}
    for name, password in passwords.items():
        register = client.post("/mobile/auth/register", json={
            "email": f"{name}@example.com", "password": password, "consent": True,
        })
        assert register.status_code == 201
        mobile[name] = {"Authorization": "Bearer " + register.json()["token"]}
    owner, other = mobile["owner"], mobile["other"]

    category = client.post("/categories", headers=owner, json={"name": "Тест"})
    assert category.status_code == 201
    category_id = category.json()["id"]
    assert client.get("/categories", headers=other).json() == []
    assert client.post("/contents", headers=other, json={"note": "Чужая категория", "category_id": category_id}).status_code == 404

    saved = client.post("/contents", headers=owner, json={
        "url": "https://example.com/reference.pdf", "category_id": category_id,
    })
    assert saved.status_code == 201
    content = saved.json()
    assert content["title"] == "example.com/reference.pdf"
    assert content["description"] is None
    content_id = content["id"]
    path = f"/contents/{content_id}"

    duplicate = client.post("/contents", headers=owner, json={"url": content["url"] + "#page=2"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["existing_id"] == content_id
    query = {"q": "reference.pdf", "source": "web", "status": "unseen", "category_id": category_id, "sort": "title", "limit": 1}
    assert client.get("/contents", headers=owner, params=query).json()["items"] == [content]
    assert client.get("/contents", headers=owner, params={**query, "offset": 1}).json()["items"] == []
    assert client.get("/contents", headers=other, params=query).json()["total"] == 0
    assert client.get(path, headers=other).status_code == 404
    assert client.patch(path, headers=other, json={"title": "Чужое изменение"}).status_code == 404
    assert client.delete(path, headers=other).status_code == 404
    assert client.post(f"{path}/open", headers=other).status_code == 404

    changed = client.patch(path, headers=owner, json={"title": "Обновлённый PDF", "status": "studied", "note": "Синтетический текст"})
    assert changed.status_code == 200
    origin = changed.json()["url"]
    assert origin == content["url"]
    assert client.post(f"{path}/open", headers=owner).status_code == 204

    login = client.post("/auth/login", headers={"Origin": ORIGIN}, json={"email": "owner@example.com", "password": passwords["owner"]})
    assert login.status_code == 200
    assert client.get("/app/").status_code == 200
    web_match = client.get("/contents", params={"q": "Обновлённый PDF", "status": "studied"}).json()
    assert web_match["total"] == 1
    assert web_match["items"][0]["id"] == content_id
    assert web_match["items"][0]["note"] == "Синтетический текст"
    assert web_match["items"][0]["open_count"] == 1
    assert client.patch(path, headers={"Origin": "https://other.example.com"}, json={"title": "Cross-site"}).status_code == 403
    assert client.patch(path, headers={"Origin": ORIGIN}, json={"title": "Изменено на сайте"}).status_code == 200
    client.cookies.clear()
    assert client.get(path, headers=owner).json()["title"] == "Изменено на сайте"

    assert client.delete(f"/categories/{category_id}", headers=owner).status_code == 204
    assert client.get(path, headers=owner).json()["category_id"] is None
    assert client.delete(path, headers=owner).status_code == 204
    assert client.get(path, headers=owner).status_code == 404
    assert client.post("/mobile/auth/logout", headers=owner, json={}).status_code == 204
    assert client.get("/contents", headers=owner).status_code == 401
