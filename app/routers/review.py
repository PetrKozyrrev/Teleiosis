from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import Field, StringConstraints, field_validator
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models import Content, ReviewAnswer, ReviewCard, ReviewCreation
from app.routers.contents import ContentId, get_own_content
from app.routers.organization import lock_owner
from app.routers.week_plan import ObjectId, PlanDay, Version, Write, matches, owned
from app.stats import user_zone

router = APIRouter(prefix="/mobile/review", tags=["review"])
OperationKey = Annotated[UUID, Header(alias="Idempotency-Key")]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]
Limit = Annotated[int, Query(ge=1, le=50)]
INTERVALS = (1, 3, 7, 14, 30, 60, 90)
CARD_LIMIT = 1000


class CardText(Write):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    takeaway: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""

    @field_validator("question", "answer", "takeaway")
    @classmethod
    def valid_text(cls, value):
        if "\x00" in value:
            raise ValueError("NUL is unsupported")
        value.encode("utf-8")
        return value


class CreateCard(CardText):
    content_id: ObjectId


class UpdateCard(CardText):
    due_on: PlanDay
    paused: bool


class AnswerInput(Write):
    rating: Literal["again", "remembered"]


def today(user):
    return datetime.now(user_zone(user.timezone)).date()


def due_card_filters(day: date):
    return (ReviewCard.paused.is_(False), ReviewCard.due_on <= day)


def card_out(card):
    return {key: getattr(card, key) for key in
            ("id", "content_id", "question", "answer", "takeaway", "due_on", "paused", "stage", "version")}


def answer_out(answer):
    return {"id": answer.id, "rating": answer.rating, "due_on": answer.due_on,
            "occurred_at": answer.occurred_at, "version": answer.previous_version + 1}


@router.get("")
def list_cards(db: DbSession, user: CurrentUser, due: bool = True, content_id: ContentId | None = None,
               limit: Limit = 20, offset: Offset = 0):
    local_day = today(user)
    filters = [ReviewCard.user_id == user.id]
    if content_id is not None:
        get_own_content(db, user, content_id)
        filters.append(ReviewCard.content_id == content_id)
    if due:
        filters.extend(due_card_filters(local_day))
    total = db.scalar(select(func.count()).select_from(ReviewCard).where(*filters))
    rows = db.execute(select(ReviewCard, Content.title).join(Content, Content.id == ReviewCard.content_id)
                      .where(*filters).order_by(ReviewCard.due_on, ReviewCard.id).limit(limit).offset(offset))
    return {"items": [dict(card_out(card), title=title) for card, title in rows],
            "total": total, "limit": limit, "offset": offset, "today": local_day}


@router.post("")
def create_card(data: CreateCard, key: OperationKey, db: DbSession, user: CurrentUser):
    lock_owner(db, user)
    fingerprint = sha256(json.dumps(data.model_dump(), sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    receipt = db.get(ReviewCreation, (user.id, key))
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise HTTPException(409, "Idempotency key reused")
        card = db.scalar(select(ReviewCard).where(ReviewCard.id == receipt.card_id, ReviewCard.user_id == user.id))
        if card is None:
            raise HTTPException(410, "Card removed")
        return card_out(card)
    get_own_content(db, user, data.content_id, lock=True)
    if db.scalar(select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == user.id)) >= CARD_LIMIT:
        raise HTTPException(409, "Card quota reached")
    card = ReviewCard(user_id=user.id, due_on=today(user), **data.model_dump())
    db.add(card)
    db.flush()
    db.add(ReviewCreation(user_id=user.id, key=key, fingerprint=fingerprint, card_id=card.id))
    db.commit()
    return card_out(card)


@router.put("/{card_id}")
def update_card(card_id: ContentId, data: UpdateCard, version: Version, db: DbSession, user: CurrentUser):
    card = owned(db, ReviewCard, user.id, card_id)
    matches(card, version)
    for key, value in data.model_dump().items():
        setattr(card, key, value)
    card.version += 1
    db.commit()
    return card_out(card)


@router.delete("/{card_id}", status_code=204)
def delete_card(card_id: ContentId, version: Version, db: DbSession, user: CurrentUser):
    card = owned(db, ReviewCard, user.id, card_id)
    matches(card, version)
    db.delete(card)
    db.commit()
    return Response(status_code=204)


@router.post("/{card_id}/answers")
def answer_card(card_id: ContentId, data: AnswerInput, key: OperationKey, version: Version,
                db: DbSession, user: CurrentUser):
    card = owned(db, ReviewCard, user.id, card_id)
    receipt = db.scalar(select(ReviewAnswer).where(ReviewAnswer.card_id == card.id, ReviewAnswer.key == key))
    previous = int(version[1:-1])
    if receipt:
        if receipt.rating != data.rating or receipt.previous_version != previous:
            raise HTTPException(409, "Idempotency key reused")
        return answer_out(receipt)
    matches(card, version)
    if card.paused:
        raise HTTPException(409, "Card paused")
    step = min(card.stage, len(INTERVALS) - 1)
    card.due_on = today(user) + timedelta(days=INTERVALS[step] if data.rating == "remembered" else 0)
    card.stage = min(card.stage + 1, len(INTERVALS)) if data.rating == "remembered" else 0
    card.version += 1
    receipt = ReviewAnswer(card_id=card.id, key=key, rating=data.rating, previous_version=previous, due_on=card.due_on)
    db.add(receipt)
    db.commit()
    return answer_out(receipt)


@router.get("/{card_id}/history")
def history(card_id: ContentId, db: DbSession, user: CurrentUser, limit: Limit = 20, offset: Offset = 0):
    owned(db, ReviewCard, user.id, card_id)
    query = select(ReviewAnswer).where(ReviewAnswer.card_id == card_id)
    rows = db.scalars(query.order_by(ReviewAnswer.id.desc()).limit(limit).offset(offset))
    return {"items": [answer_out(row) for row in rows], "offset": offset, "limit": limit,
            "total": db.scalar(select(func.count()).select_from(ReviewAnswer).where(ReviewAnswer.card_id == card_id))}
