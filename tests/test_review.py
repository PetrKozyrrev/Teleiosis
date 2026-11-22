from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.main import create_app
from app.models import Content, ReviewAnswer, ReviewCard, ReviewCreation, User
from app.routers import review
from app.sessions import create_session
from tests.helpers import auth_headers as auth

PATH = "/mobile/review"


def headers(user=1, key=None, version=1):
    return {**auth(user), "Idempotency-Key": str(key or uuid4()), "If-Match": f'"{version}"'}


def material(client, user=1):
    r = client.post("/contents", headers=auth(user), json={"note": "Synthetic review source"})
    assert r.status_code == 201
    return r.json()["id"]


def create(client, content_id=None, key=None, user=1):
    return client.post(PATH, headers=headers(user, key),
                       json={"content_id": content_id or material(client, user), "question": "Question", "answer": "Answer"})


def answer(client, card, rating="remembered", key=None, user=1):
    return client.post(f"{PATH}/{card['id']}/answers", headers=headers(user, key, card["version"]), json={"rating": rating})


def read(client, user=1, **params):
    r = client.get(PATH, params=params, headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def test_creation_replay_fingerprint_and_deleted_card(client):
    content = material(client)
    key = uuid4()
    card = create(client, content, key).json()
    assert create(client, content, key).json() == card
    assert read(client)["total"] == 1
    assert create(client, material(client), key).status_code == 409
    assert client.delete(f"{PATH}/{card['id']}", headers=headers(version=1)).status_code == 204
    assert create(client, content, key).status_code == 410
    assert read(client)["total"] == 0


def test_answer_replay_and_stale_version(client, session):
    card = create(client).json()
    key = uuid4()
    first = answer(client, card, key=key)
    assert first.status_code == 200, first.text
    assert answer(client, card, key=key).json() == first.json()
    assert answer(client, card).status_code == 412
    assert answer(client, card, rating="again", key=key).status_code == 409
    assert session.scalar(select(ReviewCard.version)) == 2
    assert len(session.scalars(select(ReviewAnswer)).all()) == 1
    card["version"] = 2
    assert answer(client, card, rating="again").status_code == 200
    # An earlier receipt remains stable even after a later answer.
    card["version"] = 1
    assert answer(client, card, key=key).json() == first.json()


def test_schedule_timezone_intervals_and_pause(client, monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 12, 31, 22, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(review, "datetime", Frozen)
    client.patch("/me/settings", headers=auth(1), json={"timezone": "Europe/Moscow"})
    card = create(client).json()
    assert card["due_on"] == "2027-01-01"
    for interval in [1, 3, 7, 14, 30, 60, 90, 90]:
        result = answer(client, card).json()
        from datetime import date, timedelta
        assert result["due_on"] == str(date(2027, 1, 1) + timedelta(days=interval))
        card["version"] += 1
    assert read(client)["total"] == 0
    result = answer(client, card, "again").json()
    card = read(client, due=False)["items"][0]
    assert card["stage"] == 0 and result["due_on"] == "2027-01-01"
    body = {k: card[k] for k in ("question", "answer", "takeaway", "due_on")}
    body["paused"] = True
    r = client.put(f"{PATH}/{card['id']}", headers=headers(version=card["version"]), json=body)
    assert r.status_code == 200
    assert read(client)["total"] == 0
    assert answer(client, r.json()).status_code == 409
    assert read(client, due=False)["total"] == 1


def test_pagination_ownership_export_and_cascade(client, session):
    content = material(client)
    for _ in range(3):
        assert create(client, content).status_code == 200
    assert read(client, limit=1, offset=1)["items"][0]["id"] != read(client, limit=1)["items"][0]["id"]
    card = read(client)["items"][0]
    assert answer(client, card).status_code == 200
    assert read(client, user=2)["total"] == 0
    assert create(client, content, user=2).status_code == 404
    assert answer(client, card, user=2).status_code == 404
    assert client.get(f"{PATH}/{card['id']}/history", headers=auth(2)).status_code == 404
    assert client.get(f"{PATH}?content_id={content}", headers=auth(2)).status_code == 404
    exported = client.get("/me/export", headers=auth(1)).json()
    assert len(exported["review_cards"]) == 3 and len(exported["review_answers"]) == 1
    assert "review_cards" not in client.get("/me/export", headers=auth(2)).json()
    assert client.delete(f"/contents/{content}", headers=auth(1)).status_code == 204
    assert session.scalar(select(ReviewAnswer.id)) is None
    assert session.scalar(select(ReviewCard.id)) is None
    assert session.scalar(select(ReviewCreation.user_id)) is not None
    session.delete(session.scalar(select(User).where(User.email == "user1@example.com")))
    session.commit()
    assert session.scalar(select(ReviewCreation.user_id)) is None


@pytest.mark.parametrize("body", [
    {"question": ""}, {"answer": " "}, {"question": "a" * 501}, {"answer": "a" * 4001},
    {"question": "bad\x00text"}, {"user_id": 2}, {"takeaway": "a" * 4001},
])
def test_invalid_input_atomicity(client, body):
    response = client.post(PATH, headers=headers(), json={"question": "Q", "answer": "A", "content_id": material(client), **body})
    assert response.status_code == 422
    assert read(client)["total"] == 0


def test_auth_quota_and_history_pagination(client, monkeypatch):
    assert client.get(PATH).status_code == 401
    monkeypatch.setattr(review, "CARD_LIMIT", 1)
    card = create(client).json()
    assert create(client).status_code == 409
    for _ in range(3):
        r = answer(client, card, "again")
        assert r.status_code == 200
        card["version"] += 1
    hist = f"{PATH}/{card['id']}/history"
    page = client.get(hist+"?limit=1", headers=auth(1)).json()
    next_page = client.get(hist+"?limit=1&offset=1", headers=auth(1)).json()
    assert page["total"] == 3 and page["items"][0]["id"] > next_page["items"][0]["id"]


def test_concurrent_answers_count_once(engine):
    with Session(engine) as db:
        user = User(email=f"review-{uuid4().hex}@example.com")
        db.add(user); db.flush()
        content = Content(user_id=user.id, title="Synthetic", note="Synthetic")
        db.add(content); db.flush()
        card = ReviewCard(user_id=user.id, content_id=content.id, question="Q", answer="A", due_on=datetime.now().date())
        db.add(card); db.commit()
        token, _ = create_session(db, user, client_type="mobile")
        card_id, owner = card.id, user.id
    def send():
        app = create_app()
        def sessions():
            with Session(engine) as db:
                yield db
        app.dependency_overrides[get_db] = sessions
        with TestClient(app) as client:
            return client.post(f"{PATH}/{card_id}/answers",
                headers={"Authorization": "Bearer "+token, "If-Match": '"1"', "Idempotency-Key": str(uuid4())},
                json={"rating": "remembered"}).status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(lambda _: send(), range(2))) == [200, 412]
        with Session(engine) as db:
            assert len(db.scalars(select(ReviewAnswer).where(ReviewAnswer.card_id == card_id)).all()) == 1
    finally:
        with Session(engine) as db:
            db.delete(db.get(User, owner)); db.commit()
