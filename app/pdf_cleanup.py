"""One-shot cleanup for the private PDF bucket. Run periodically with API settings."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app import pdf_storage as storage
from app.config import settings
from app.db import SessionLocal
from app.models import PdfObject


def cleanup(db, *, now: datetime, limit: int = 50) -> tuple[int, int]:
    rows = db.scalars(select(PdfObject).where(
        or_(PdfObject.charged_user_id.is_(None),
            PdfObject.user_id.is_(None) & PdfObject.creating.is_(False),
            PdfObject.published.is_(False) & (PdfObject.created_at < now - timedelta(hours=1))),
    ).order_by(PdfObject.created_at, PdfObject.id).limit(limit).with_for_update(skip_locked=True)).all()
    failed = 0
    for item in rows:
        try:
            storage.delete_pdf_object(item.id)
        except storage.PdfServiceUnavailable:
            failed += 1
        else:
            db.delete(item)
    db.commit()
    return len(rows) - failed, failed


def main():
    if not settings.pdf_enabled:
        raise SystemExit("PDF cleanup requires the configured private bucket")
    with SessionLocal() as db:
        removed, failed = cleanup(db, now=datetime.now(timezone.utc))
    print(f"PDF objects cleaned: {removed}; failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
