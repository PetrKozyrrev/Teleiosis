from app.models import Content
from tests.helpers import auth_headers as auth


def save(client, telegram_id=1, **body):
    response = client.post("/contents", json=body, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()


def listing(client, telegram_id=1, **params):
    return client.get("/contents", params=params, headers=auth(telegram_id))


def titles(response):
    return [item["title"] for item in response.json()["items"]]


def test_requires_auth(client):
    assert client.get("/contents").status_code == 401


def test_empty_library(client):
    response = listing(client)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_default_order_newest_first(client):
    for name in ("A", "B", "C"):
        save(client, note=f"заметка {name}", title=name)
    assert titles(listing(client)) == ["C", "B", "A"]


def test_sort_oldest_and_title(client):
    for name in ("b", "A", "c"):
        save(client, note=f"заметка {name}", title=name)
    assert titles(listing(client, sort="oldest")) == ["b", "A", "c"]
    assert titles(listing(client, sort="title")) == ["A", "b", "c"]


def test_pagination(client):
    for i in range(5):
        save(client, note=f"заметка {i}", title=f"T{i}")
    page = listing(client, limit=2, offset=2)
    assert page.json()["total"] == 5
    assert titles(page) == ["T2", "T1"]
    assert titles(listing(client, limit=2, offset=4)) == ["T0"]
    beyond = listing(client, limit=2, offset=10)
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 5


def test_search_by_title_case_insensitive(client):
    save(client, note="x", title="Маркетинг для начинающих")
    save(client, note="y", title="Python basics")
    assert titles(listing(client, q="МАРКЕТИНГ")) == ["Маркетинг для начинающих"]
    assert titles(listing(client, q="  python  ")) == ["Python basics"]
    assert titles(listing(client, q="zzz")) == []
    assert listing(client, q="   ").json()["total"] == 2


def test_search_treats_wildcards_literally(client):
    for name in ("100% done", "100 done", "a_b", "axb"):
        save(client, note=name, title=name)
    assert titles(listing(client, q="100%")) == ["100% done"]
    assert titles(listing(client, q="a_b")) == ["a_b"]


def test_filter_by_status(client, session):
    a = save(client, note="a", title="A")
    save(client, note="b", title="B")
    session.get(Content, a["id"]).status = "studied"
    session.flush()
    assert titles(listing(client, status="studied")) == ["A"]
    assert titles(listing(client, status="unseen")) == ["B"]


def test_filter_by_source(client):
    save(client, url="https://youtu.be/dQw4w9WgXcQ", title="Video")
    save(client, url="https://example.com/a", title="Site")
    save(client, note="n", title="Note")
    assert titles(listing(client, source="youtube")) == ["Video"]
    assert titles(listing(client, source="web")) == ["Site"]
    assert titles(listing(client, source="other")) == ["Note"]


def test_filter_by_category_and_uncategorized(client):
    category = client.post(
        "/categories", json={"name": "Бизнес"}, headers=auth(1)
    ).json()
    save(client, url="https://example.com/a", title="In", category_id=category["id"])
    save(client, url="https://example.com/b", title="Out")
    assert titles(listing(client, category_id=category["id"])) == ["In"]
    assert titles(listing(client, uncategorized="true")) == ["Out"]


def test_category_and_uncategorized_conflict(client):
    assert listing(client, category_id=1, uncategorized="true").status_code == 422


def test_invalid_params_rejected(client):
    for params in (
        {"status": "done"},
        {"source": "vk"},
        {"sort": "random"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"category_id": 0},
    ):
        assert listing(client, **params).status_code == 422, params


def test_only_own_items(client):
    category = client.post(
        "/categories", json={"name": "Моя"}, headers=auth(1)
    ).json()
    save(client, 1, url="https://example.com/a", title="Мой", category_id=category["id"])

    assert listing(client, 2).json()["total"] == 0
    other = listing(client, 2, category_id=category["id"])
    assert other.status_code == 200
    assert other.json()["items"] == []
    assert titles(listing(client, 1)) == ["Мой"]