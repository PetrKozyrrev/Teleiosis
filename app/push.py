"""Opt-in RuStore delivery with durable receipts; email retains its own rules."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import random
from uuid import uuid4
from time import monotonic

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.digest import is_due, pick_materials
from app.models import AuthSession, Content, PushDelivery, PushDevice, Reminder, User
from app.sessions import SESSION_ABSOLUTE
from app.stats import user_zone

REMINDER_TTL = timedelta(hours=24)
DIGEST_TTL = timedelta(hours=3)
LEASE = timedelta(seconds=45)
ACTIVE = ("pending", "sending", "retry_wait")


@dataclass(frozen=True)
class SendResult:
    outcome: str
    retry_after: int = 0


def send_rustore(token: str, delivery: PushDelivery, now: datetime) -> SendResult:
    remaining = math.floor((delivery.expires_at - now).total_seconds())
    if remaining <= 0:
        return SendResult("expired")
    message = {
        "token": token,
        "notification": {"title": "Телеосис", "body": "Пора вернуться к материалу в библиотеке"},
        "data": {"content_id": str(delivery.content_id), "delivery_id": str(delivery.id)},
        "android": {"ttl": f"{remaining}s"},
    }
    try:
        response = httpx.post(
            f"https://vkpns.rustore.ru/v1/projects/{settings.rustore_project_id}/messages:send",
            json={"message": message},
            headers={"Authorization": "Bearer " + settings.rustore_service_token.get_secret_value()},
            timeout=10, follow_redirects=False,
        )
    except httpx.HTTPError:
        return SendResult("retry")
    if response.status_code == 200:
        return SendResult("accepted")
    if response.status_code == 429 or response.status_code >= 500:
        retry = response.headers.get("Retry-After", "")
        return SendResult("retry", min(int(retry), 86_400) if retry.isdecimal() else 0)
    if response.status_code in (400, 404):
        try:
            error = response.json().get("error", {})
        except (ValueError, AttributeError):
            error = {}
        if response.status_code == 404 and isinstance(error, dict) and error.get("status") in ("NOT_FOUND", "UNREGISTERED"):
            return SendResult("invalid")
        if isinstance(error, dict) and error.get("status") == "INVALID_ARGUMENT" and error.get("message") == "The registration token is not a valid FCM registration token":
            return SendResult("invalid")
    # Payload and credential errors retain the token for operator diagnosis.
    return SendResult("failed")


def session_valid(session: AuthSession, now: datetime) -> bool:
    return session.client_type == "mobile" and session.expires_at > now and session.created_at + SESSION_ABSOLUTE > now


def plan_deliveries(db: Session, now: datetime) -> int:
    count = 0
    devices = db.scalars(select(PushDevice).join(AuthSession, PushDevice.session_id == AuthSession.id).where(
        PushDevice.enabled.is_(True), AuthSession.client_type == "mobile",
        AuthSession.expires_at > now, AuthSession.created_at > now - SESSION_ABSOLUTE,
    )).all()
    for device in devices:
        user = db.get(User, device.user_id)
        due = db.scalars(select(Reminder).join(Content, Reminder.content_id == Content.id).where(
            Reminder.user_id == device.user_id, Content.user_id == device.user_id,
            # Plan before the email pass consumes pending reminders. Existing
            # receipts may still retry after email marks their parent sent.
            Reminder.status == "pending", Reminder.scheduled_at <= now,
            Reminder.scheduled_at > now - REMINDER_TTL,
            Reminder.scheduled_at >= device.enabled_at,
            Content.status.in_(("unseen", "planned")),
        )).all()
        events = [(f"reminder/{reminder.id}/{reminder.scheduled_at.isoformat()}", reminder.content_id,
                   reminder.id, reminder.scheduled_at, reminder.scheduled_at + REMINDER_TTL) for reminder in due]
        local = now.astimezone(user_zone(user.timezone))
        if is_due(local, user.reminder_time, None):
            items, _ = pick_materials(db, user.id)
            if items:
                start = local.replace(hour=user.reminder_time.hour, minute=user.reminder_time.minute, second=0, microsecond=0)
                scheduled = start.astimezone(timezone.utc)
                if device.enabled_at <= scheduled:
                    events.append((f"digest/{local.date().isoformat()}", items[0][0], None, scheduled, scheduled + DIGEST_TTL))
        for event_key, content_id, reminder_id, scheduled_at, expires_at in events:
            result = db.execute(insert(PushDelivery).values(
                id=uuid4(), device_id=device.id, content_id=content_id, reminder_id=reminder_id,
                event_key=event_key, scheduled_at=scheduled_at, expires_at=expires_at, next_attempt_at=now,
                status="pending", attempts=0,
            ).on_conflict_do_nothing(index_elements=["device_id", "event_key"]))
            count += result.rowcount
    db.commit()
    return count


def cancel_for_content(db: Session, user_id: int, content_id: int):
    db.execute(update(PushDelivery).where(
        PushDelivery.content_id == content_id, PushDelivery.status.in_(ACTIVE),
        PushDelivery.device_id.in_(select(PushDevice.id).where(PushDevice.user_id == user_id)),
    ).values(status="cancelled", reason="changed"))


def eligible(db: Session, delivery: PushDelivery, now: datetime) -> PushDevice | None:
    device = db.get(PushDevice, delivery.device_id)
    content = db.get(Content, delivery.content_id)
    if not device or not device.enabled or not content or content.user_id != device.user_id:
        return None
    if content.status not in ("unseen", "planned") or device.enabled_at > delivery.scheduled_at:
        return None
    session = db.get(AuthSession, device.session_id)
    if not session or session.user_id != device.user_id or not session_valid(session, now):
        return None
    user = db.get(User, device.user_id)
    if delivery.reminder_id is not None:
        reminder = db.get(Reminder, delivery.reminder_id)
        if not reminder or reminder.user_id != device.user_id or reminder.status == "cancelled" or reminder.scheduled_at != delivery.scheduled_at:
            return None
    else:
        local = now.astimezone(user_zone(user.timezone))
        if delivery.event_key != f"digest/{local.date().isoformat()}" or not is_due(local, user.reminder_time, None):
            return None
        if delivery.scheduled_at.astimezone(user_zone(user.timezone)).time().replace(tzinfo=None) != user.reminder_time:
            return None
    return device


def process_push(db: Session, now: datetime, send=send_rustore, *, limit=50) -> int:
    if not settings.push_enabled:
        return 0
    started = monotonic()
    db.expire_all()
    plan_deliveries(db, now)
    ids = db.scalars(select(PushDelivery.id).where(
        PushDelivery.status.in_(ACTIVE), PushDelivery.next_attempt_at <= now,
    ).order_by(PushDelivery.next_attempt_at, PushDelivery.id).limit(limit)).all()
    accepted = 0
    for delivery_id in ids:
        current = now + timedelta(seconds=monotonic() - started)
        claimed = db.execute(update(PushDelivery).where(
            PushDelivery.id == delivery_id, PushDelivery.status.in_(ACTIVE), PushDelivery.next_attempt_at <= current,
        ).values(status="sending", attempts=PushDelivery.attempts + 1, next_attempt_at=current + LEASE).returning(PushDelivery.id)).scalar()
        db.commit()
        if claimed is None:
            continue
        db.expire_all()
        delivery = db.get(PushDelivery, delivery_id, populate_existing=True)
        if delivery is None:
            continue
        device = eligible(db, delivery, current)
        if device is None:
            delivery.status, delivery.reason = "cancelled", "ineligible"
        elif delivery.expires_at <= current:
            delivery.status, delivery.reason = "expired", "ttl"
        else:
            # Snapshot IDs and token before releasing the transaction for network I/O.
            token = device.token
            device_id = device.id
            db.commit()
            try:
                result = send(token, delivery, current)
            except Exception:
                # Provider exceptions may contain credentials. Never log their text.
                result = SendResult("retry")
            # Logout or deletion while sending can cascade-delete the receipt.
            db.expire_all()
            delivery = db.get(PushDelivery, delivery_id)
            if delivery is None or delivery.status != "sending":
                continue
            device = db.get(PushDevice, device_id)
            if result.outcome == "accepted":
                delivery.status, delivery.reason = "accepted", None
                accepted += 1
            elif result.outcome == "invalid":
                delivery.status, delivery.reason = "failed", "invalid_token"
                if device is not None and device.token == token:
                    device.enabled, device.token = False, ""
            elif result.outcome == "retry":
                seconds = max(result.retry_after, min(3600, 15 * 2 ** min(delivery.attempts - 1, 8)) * random.uniform(0.8, 1.2))
                delivery.status, delivery.reason = "retry_wait", "provider"
                delivery.next_attempt_at = current + timedelta(seconds=seconds)
            else:
                delivery.status = "expired" if result.outcome == "expired" else "failed"
                delivery.reason = "provider"
        db.commit()
    db.execute(delete(PushDelivery).where(
        PushDelivery.status.not_in(ACTIVE), PushDelivery.scheduled_at < now - timedelta(days=30),
    ))
    db.commit()
    return accepted
