from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, select, text

from app.activity import record_activity
from app.models import User, UserActivity
from tests.helpers import auth_headers as auth

NOW = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)  # Владивосток: уже 12.11, 06:00


def days_of(session):
    return session.scalars(select(UserActivity.day).order_by(UserActivity.day)).all()


def count(session):
    return session.scalar(select(func.count()).select_from(UserActivity))


def make_user(session, tz="UTC"):
    user = User(email="a@example.com", timezone=tz)
    session.add(user)
    session.flush()
    return user


# ---------- сама запись ----------


def test_records_the_local_day_once(session):
    user = make_user(session)
    record_activity(session, user, now=NOW)
    record_activity(session, user, now=NOW + timedelta(hours=1))
    assert days_of(session) == [date(2026, 11, 11)]


def test_next_day_is_a_new_row(session):
    user = make_user(session)
    record_activity(session, user, now=NOW)
    record_activity(session, user, now=NOW + timedelta(days=1))
    assert days_of(session) == [date(2026, 11, 11), date(2026, 11, 12)]


def test_day_follows_the_user_timezone(session):
    user = make_user(session, tz="Asia/Vladivostok")
    record_activity(session, user, now=NOW)
    assert days_of(session) == [date(2026, 11, 12)]


def test_unknown_timezone_falls_back_to_utc(session):
    user = make_user(session, tz="Europe/Nowhere")
    record_activity(session, user, now=NOW)
    assert days_of(session) == [date(2026, 11, 11)]


def test_days_are_per_user(session):
    first = make_user(session)
    second = User(email="b@example.com")
    session.add(second)
    session.flush()
    record_activity(session, first, now=NOW)
    record_activity(session, second, now=NOW)
    assert count(session) == 2


def test_failure_is_swallowed_and_rolled_back():
    class BrokenDb:
        rolled_back = False

        def execute(self, *args, **kwargs):
            raise RuntimeError("db down")

        def commit(self):
            raise AssertionError("must not commit after a failure")

        def rollback(self):
            self.rolled_back = True

    db = BrokenDb()
    record_activity(db, SimpleNamespace(id=1, timezone="UTC"), now=NOW)
    assert db.rolled_back is True


def test_deleting_the_user_removes_activity(session):
    user = make_user(session)
    record_activity(session, user, now=NOW)
    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert count(session) == 0


# ---------- что считается действием ----------


def save(client, **body):
    return client.post("/contents", json=body, headers=auth(1))


def clear(session):
    session.execute(text("DELETE FROM user_activity"))


def test_saving_a_material_counts(client, session):
    assert save(client, note="x").status_code == 201
    assert count(session) == 1


def test_changing_a_material_counts(client, session):
    item = save(client, note="x").json()
    clear(session)
    response = client.patch(f"/contents/{item['id']}", json={"status": "studied"}, headers=auth(1))
    assert response.status_code == 200
    assert count(session) == 1


def test_opening_the_original_counts(client, session):
    item = save(client, url="https://example.com/a").json()
    clear(session)
    assert client.post(f"/contents/{item['id']}/open", headers=auth(1)).status_code == 204
    assert count(session) == 1


def test_setting_a_reminder_counts(client, session):
    item = save(client, note="x").json()
    clear(session)
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    response = client.put(
        f"/contents/{item['id']}/reminder", json={"scheduled_at": when}, headers=auth(1)
    )
    assert response.status_code == 200
    assert count(session) == 1


def test_reading_and_housekeeping_do_not_count(client, session):
    item = save(client, note="x").json()
    clear(session)
    assert client.get("/me", headers=auth(1)).status_code == 200
    assert client.get("/contents", headers=auth(1)).status_code == 200
    assert client.get(f"/contents/{item['id']}", headers=auth(1)).status_code == 200
    assert client.get("/stats", headers=auth(1)).status_code == 200
    assert client.get("/categories", headers=auth(1)).status_code == 200
    assert client.get(f"/contents/{item['id']}/reminder", headers=auth(1)).status_code == 200
    assert client.post("/categories", json={"name": "A"}, headers=auth(1)).status_code == 201
    assert client.patch("/me/settings", json={"timezone": "UTC"}, headers=auth(1)).status_code == 200
    assert client.delete(f"/contents/{item['id']}", headers=auth(1)).status_code == 204
    assert count(session) == 0


def test_failed_actions_do_not_count(client, session):
    item = save(client, url="https://example.com/a").json()
    clear(session)
    assert save(client, url="https://example.com/a").status_code == 409
    assert save(client, url="ftp://bad").status_code == 422
    assert client.patch(f"/contents/{item['id']}", json={"title": ""}, headers=auth(1)).status_code == 422
    assert client.patch("/contents/999999", json={"title": "x"}, headers=auth(1)).status_code == 404
    assert client.post("/contents/999999/open", headers=auth(1)).status_code == 404
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    response = client.put(
        f"/contents/{item['id']}/reminder", json={"scheduled_at": past}, headers=auth(1)
    )
    assert response.status_code == 422
    assert count(session) == 0