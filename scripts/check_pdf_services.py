"""Smoke test for private PDF I/O on disposable loopback services."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import PdfObject
from app.pdf_cleanup import cleanup
from app.pdf_storage import s3


def main() -> None:
    db = make_url(settings.database_url)
    if (not settings.pdf_enabled or settings.app_env != "dev" or db.host != "127.0.0.1"
        or not (db.database or "").endswith("_migration_test")
        or urlsplit(settings.pdf_s3_endpoint).hostname != "127.0.0.1"
        or settings.pdf_scanner_host != "127.0.0.1"):
        raise SystemExit("Use enabled PDF settings with disposable loopback services only")
    with SessionLocal() as session:
        if session.scalar(select(PdfObject.id).limit(1)) is not None:
            raise SystemExit("PDF ledger must be empty before the local smoke test")

    suffix = uuid4().hex[:12]
    bucket = f"teleiosis-pdf-test-{suffix}"
    settings.pdf_s3_bucket = bucket
    store = s3()
    store.create_bucket(Bucket=bucket)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = BytesIO()
    writer.write(stream)
    data = stream.getvalue()
    accounts = []
    password = "synthetic-PDF-services-only"
    try:
        with TestClient(app) as client:
            try:
                for label in ("a", "b"):
                    issued = client.post("/mobile/auth/register", json={
                        "email": f"pdf-{label}-{suffix}@example.com", "password": password, "consent": True,
                    })
                    assert issued.status_code == 201
                    accounts.append({"Authorization": "Bearer " + issued.json()["token"]})
                owner, other = accounts
                create = "/mobile/library/pdf"
                assert client.get(create, headers=owner).status_code == 204
                headers = {**owner, "Content-Type": "application/pdf"}
                result = client.post(create, headers=headers, content=data)
                assert result.status_code == 201, (result.status_code, result.json().get("detail"))
                material = result.json()
                assert material["content_type"] == "pdf" and material["url"] is None
                assert client.post(create, headers=headers, content=data).json() == material
                path = f"/mobile/library/contents/{material['id']}/pdf"
                objects = store.list_objects_v2(Bucket=bucket)["Contents"]
                assert len(objects) == 1
                try:
                    with urlopen(f"{settings.pdf_s3_endpoint.rstrip('/')}/{bucket}/{objects[0]['Key']}", timeout=5):
                        raise AssertionError("Unsigned object read succeeded")
                except HTTPError as error:
                    assert error.code == 403, "Unexpected unsigned access result"
                assert client.get(path + "/download", headers=other).status_code == 404
                assert client.get(path + "/download", headers=owner).content == data
                assert client.delete(f"/contents/{material['id']}", headers=owner).status_code == 204
                assert client.get(path + "/download", headers=owner).status_code == 404
                with SessionLocal() as session:
                    assert cleanup(session, now=datetime.now(timezone.utc)) == (1, 0)
                assert store.list_objects_v2(Bucket=bucket)["KeyCount"] == 0
            finally:
                for headers in accounts:
                    client.post("/auth/delete-account", headers=headers, json={"password": password})
                with SessionLocal() as session:
                    _removed, failed = cleanup(session, now=datetime.now(timezone.utc))
                    if failed:
                        print("Synthetic PDF cleanup will be retried on the isolated services", file=sys.stderr)
    finally:
        # The bucket is unique and created above. Never reuse a pre-existing bucket.
        for item in store.list_objects_v2(Bucket=bucket).get("Contents", []):
            store.delete_object(Bucket=bucket, Key=item["Key"])
        store.delete_bucket(Bucket=bucket)
    print("Private PDF services passed: ClamAV scan, S3 upload/replay, unsigned denial, owner download and physical cleanup")


if __name__ == "__main__":
    main()
