from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text

from app.models import User
from app.stats import compute_stats
from tests.helpers import auth_headers as auth

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def save(client, telegram_id=1, **body):
    response = client.post("/contents", json=body, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, content_id, status, telegram_id=1):
    response = client.patch(
        f"/contents/{content_id}", json={"status": status}, headers=auth(telegram_id)
    )
    assert response.status_code == 200, response.text


def make_category(client, name, telegram_id=1):
    response = client.post("/categories", json={"name": name}, headers=auth(telegram_id))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def stats(client, telegram_id=1):
    response = client.get("/stats", headers=auth(telegram_id))
    assert response.status_code == 200, response.text
    return response.json()


def user_of(session, telegram_id=1):
    return session.scalar(select(User).where(User.telegram_id == telegram_id))


def set_created(session, content_id, moment):
    session.execute(
        text("UPDATE contents SET created_at = :ts WHERE id = :id"),
        {"ts": moment, "id": content_id},
    )


def set_studied(session, content_id, moment):
    session.execute(
        text("UPDATE contents SET status = 'studied', studied_at = :ts WHERE id = :id"),
        {"ts": moment, "id": content_id},
    )


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ---------- API ----------


def test_requires_auth(client):
    assert client.get("/stats").status_code == 401


def test_empty_library(client):
    response = client.get("/stats", headers=auth(1))
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["total"] == 0
    assert body["by_status"] == {"unseen": 0, "planned": 0, "studied": 0, "irrelevant": 0}
    assert body["studied_share"] is None
    assert body["return_share"] is None
    assert body["top_categories"] == []
    assert len(body["days"]) == 7
    assert all(d["added"] == 0 and d["studied"] == 0 for d in body["days"])


def test_counts_and_studied_share(client):
    ids = [save(client, note=f"заметка {i}")["id"] for i in range(5)]
    set_status(client, ids[0], "studied")
    set_status(client, ids[1], "studied")
    set_status(client, ids[2], "irrelevant")
    set_status(client, ids[3], "planned")

    body = stats(client)
    assert body["total"] == 5
    assert body["by_status"] == {"unseen": 1, "planned": 1, "studied": 2, "irrelevant": 1}
    assert body["studied_share"] == pytest.approx(0.5, abs=1e-4)  # 2 из 5 минус 1


def test_studied_share_is_none_when_everything_is_irrelevant(client):
    set_status(client, save(client, note="x")["id"], "irrelevant")
    body = stats(client)
    assert body["total"] == 1
    assert body["studied_share"] is None


def test_return_share_counts_only_materials_with_a_link(client):
    first = save(client, url="https://example.com/a")
    save(client, url="https://example.com/b")
    save(client, note="только заметка")
    assert client.post(f"/contents/{first['id']}/open", headers=auth(1)).status_code == 204
    assert client.post(f"/contents/{first['id']}/open", headers=auth(1)).status_code == 204

    body = stats(client)
    assert body["with_url"] == 2
    assert body["opened"] == 1  # материал, а не число открытий
    assert body["return_share"] == pytest.approx(0.5, abs=1e-4)


def test_return_share_is_none_for_notes_only(client):
    save(client, note="x")
    body = stats(client)
    assert body["with_url"] == 0
    assert body["return_share"] is None


def test_top_categories_sorted_limited_and_without_empty_ones(client):
    plan = {"B": 2, "A": 3, "C": 1, "D": 1, "E": 1, "F": 1, "G": 1}
    for name, amount in plan.items():
        category_id = make_category(client, name)
        for i in range(amount):
            save(client, note=f"{name}{i}", category_id=category_id)
    make_category(client, "Z")  # пустая

    top = stats(client)["top_categories"]
    assert [(c["name"], c["count"]) for c in top] == [
        ("A", 3), ("B", 2), ("C", 1), ("D", 1), ("E", 1),
    ]


def test_stats_are_per_user(client):
    category_id = make_category(client, "Моя")
    set_status(client, save(client, 1, note="x", category_id=category_id)["id"], "studied")

    other = stats(client, 2)
    assert other["total"] == 0
    assert other["top_categories"] == []
    assert other["by_status"]["studied"] == 0
    assert stats(client, 1)["total"] == 1


# ---------- окно 7 дней (время задаётся аргументом) ----------


def test_week_window_in_utc(client, session):
    today = save(client, note="сегодня")["id"]
    first_day = save(client, note="первый день окна")["id"]
    outside = save(client, note="вне окна")["id"]
    set_created(session, today, utc(2026, 11, 11, 8, 0))
    set_created(session, first_day, utc(2026, 11, 5, 0, 0))
    set_created(session, outside, utc(2026, 11, 4, 23, 59))

    result = compute_stats(session, user_of(session), now=NOW)
    assert [d["day"] for d in result["days"]] == [date(2026, 11, d) for d in range(5, 12)]
    assert result["days"][-1]["added"] == 1
    assert result["days"][0]["added"] == 1
    assert result["added_7d"] == 2
    assert result["added_7d"] == sum(d["added"] for d in result["days"])
    assert result["total"] == 3  # итоги не зависят от окна


def test_week_uses_the_user_timezone(client, session):
    in_today = save(client, note="по UTC вчера, по Владивостоку сегодня")["id"]
    first_day = save(client, note="первый местный день окна")["id"]
    outside = save(client, note="вне окна")["id"]
    set_created(session, in_today, utc(2026, 11, 10, 20, 0))  # местное 11.11 06:00
    set_created(session, first_day, utc(2026, 11, 4, 15, 0))  # местное 05.11 01:00
    set_created(session, outside, utc(2026, 11, 4, 13, 0))  # местное 04.11 23:00
    user = user_of(session)
    user.timezone = "Asia/Vladivostok"
    session.flush()

    result = compute_stats(session, user, now=NOW)
    assert result["days"][0]["day"] == date(2026, 11, 5)
    assert result["days"][-1]["day"] == date(2026, 11, 11)
    assert result["days"][-1]["added"] == 1
    assert result["days"][0]["added"] == 1
    assert result["added_7d"] == 2


def test_studied_dynamics(client, session):
    recent = save(client, note="недавно")["id"]
    old = save(client, note="давно")["id"]
    set_studied(session, recent, utc(2026, 11, 11, 11, 0))
    set_studied(session, old, utc(2026, 11, 1, 10, 0))

    result = compute_stats(session, user_of(session), now=NOW)
    assert result["by_status"]["studied"] == 2
    assert result["studied_7d"] == 1
    assert result["days"][-1]["studied"] == 1


def test_unknown_user_timezone_falls_back_to_utc(client, session):
    save(client, note="x")
    user = user_of(session)
    user.timezone = "Europe/Nowhere"
    session.flush()

    result = compute_stats(session, user, now=NOW)
    assert result["days"][-1]["day"] == date(2026, 11, 11)