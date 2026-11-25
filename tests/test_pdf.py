from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import quote

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select

from app import pdf_storage as storage
from app.config import settings
from app.models import PdfObject
from app.pdf_cleanup import cleanup
from tests.helpers import auth_headers


def sample_pdf(*, width=100, protected=False, active=False):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=100)
    if protected:
        writer.encrypt("synthetic")
    if active:
        writer.root_object[NameObject("/OpenAction")] = NameObject("/None")
    data = BytesIO()
    writer.write(data)
    return data.getvalue()


def test_counts_only_text_from_pdf_pages():
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    name = NameObject
    page[name("/Resources")] = DictionaryObject({name("/Font"): DictionaryObject({
        name("/F1"): DictionaryObject({name("/Type"): name("/Font"), name("/Subtype"): name("/Type1"),
                                       name("/BaseFont"): name("/Helvetica")}),
    })})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 10 Tf 10 30 Td (Synthetic text) Tj ET")
    page.replace_contents(stream)
    data = BytesIO()
    writer.write(data)

    assert storage.pdf_character_count(data.getvalue()) == len("Synthetic text")
    assert storage.pdf_character_count(sample_pdf()) is None


CREATE = "/mobile/library/pdf"


def pdf_path(material):
    return f"/mobile/library/contents/{material['id']}/pdf"


def upload(client, headers, data, name="Спецификация.pdf", title="", category=None):
    return client.post(CREATE, headers={
        **headers, "Content-Type": "application/pdf", "X-Teleiosis-Filename": quote(name, safe=""),
        "X-Teleiosis-Pdf-Title": quote(title, safe=""),
    }, params={} if category is None else {"category_id": category}, content=data)


class Scanner:
    def __init__(self, response=b"stream: OK\0"):
        self.response = response
        self.sent = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, _size):
        prefix, self.response = self.response[:4], self.response[4:]
        return prefix


@pytest.fixture
def pdf_services(monkeypatch):
    blobs, scanner = {}, Scanner()
    monkeypatch.setattr(settings, "pdf_enabled", True)
    monkeypatch.setattr(storage.socket, "create_connection", lambda *_args, **_kwargs: scanner)
    monkeypatch.setattr(storage, "put_pdf", lambda key, data: blobs.__setitem__(key, data))
    monkeypatch.setattr(storage, "get_pdf", lambda key, _size: blobs[key])
    monkeypatch.setattr(storage, "delete_pdf_object", lambda key: blobs.pop(key, None))
    return blobs, scanner


def test_pdf_create_replay_export_download_and_owner_isolation(client, session, pdf_services):
    owner, other = auth_headers(1), auth_headers(2)
    category = client.post("/categories", headers=owner, json={"name": "PDF category"}).json()["id"]
    data = sample_pdf()
    assert client.get(CREATE, headers=owner).status_code == 204
    assert upload(client, other, data, category=category).json()["detail"]["code"] == "pdf_category_missing"
    assert upload(client, {**owner, "Origin": "https://example.net"}, data).status_code == 403
    response = upload(client, owner, data, title="Мой PDF", category=category)
    assert response.status_code == 201, response.text
    material = response.json()
    path = pdf_path(material)
    assert material["content_type"] == "pdf" and material["title"] == "Мой PDF"
    assert material["url"] is None and material["note"] is None and material["category_id"] == category
    assert client.get("/contents", headers=owner).json()["items"] == [material]
    assert client.get("/contents", headers=other).json()["total"] == 0
    assert upload(client, owner, data, "Новое имя.pdf", title="Другое название").json() == material
    blobs, scanner = pdf_services
    assert len(blobs) == 1
    assert scanner.sent == b"zINSTREAM\0" + len(data).to_bytes(4, "big") + data + bytes(4)
    assert client.get(path, headers=owner).json() == {"name": "Спецификация.pdf", "size_bytes": len(data), "published": True}
    assert client.put(path, headers=owner, content=data).status_code == 405
    assert client.get(path + "/download", headers=other).status_code == 404
    downloaded = client.get(path + "/download", headers=owner)
    assert downloaded.status_code == 200 and downloaded.content == data
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.headers["content-disposition"].endswith(quote("Спецификация.pdf", safe=""))
    assert downloaded.headers["cache-control"] == "no-store"
    exported = client.get("/me/export", headers=owner).json()
    assert exported["contents"][0]["note"] == "Мой PDF"
    assert exported["pdf_attachments"][0]["content_id"] == material["id"]
    assert set(exported["pdf_attachments"][0]) == {"content_id", "name", "size_bytes", "sha256"}
    assert "pdf_attachments" not in client.get("/me/export", headers=other).json()
    assert client.post("/mobile/library/imports/preview", headers=other, json=exported).status_code == 200
    changed = client.patch(f"/contents/{material['id']}", headers=owner, json={"note": "Optional"})
    assert changed.status_code == 200
    assert client.patch(f"/contents/{material['id']}", headers=owner, json={"note": None}).status_code == 200
    scanner.response = b"stream: OK\0"
    assert upload(client, other, data).status_code == 201
    assert len(blobs) == 2
    assert client.delete(f"/contents/{material['id']}", headers=owner).status_code == 204
    assert client.get(path + "/download", headers=owner).status_code == 404
    assert cleanup(session, now=datetime.now(timezone.utc)) == (1, 0)
    assert len(blobs) == 1


@pytest.mark.parametrize(("data", "signature", "status", "code"), [
    (b"not a PDF", b"stream: OK\0", 422, "invalid_pdf"),
    (b"%PDF-1.4\ninvalid\n%%EOF\n", b"stream: OK\0", 422, "unsupported_pdf"),
    (sample_pdf(protected=True), b"stream: OK\0", 422, "unsupported_pdf"),
    (sample_pdf(active=True), b"stream: OK\0", 422, "unsupported_pdf"),
    (sample_pdf(), b"stream: synthetic FOUND\0", 422, "unsafe_pdf"),
    (sample_pdf(), b"INSTREAM size limit exceeded. ERROR\0", 503, "pdf_service_unavailable"),
])
def test_pdf_rejects_invalid_or_unsafe_input_without_storing(client, session, pdf_services, data, signature, status, code):
    headers = auth_headers(1)
    blobs, scanner = pdf_services
    scanner.response = signature
    response = upload(client, headers, data)
    assert response.status_code == status and response.json()["detail"]["code"] == code
    assert not blobs and session.scalar(select(PdfObject)) is None
    assert client.get("/contents", headers=headers).json()["total"] == 0


def test_pdf_feature_flags_mime_limits_and_filename(client, monkeypatch, pdf_services):
    headers = auth_headers(1)
    monkeypatch.setattr(settings, "pdf_enabled", False)
    assert client.get(CREATE, headers=headers).json()["detail"]["code"] == "pdf_disabled"
    assert upload(client, headers, sample_pdf()).status_code == 503
    assert client.get(CREATE).status_code == 401
    monkeypatch.setattr(settings, "pdf_enabled", True)
    assert client.post(CREATE, headers=headers, content=b"garbage").status_code == 415
    assert upload(client, headers, sample_pdf(), "../../file.pdf").status_code == 422
    assert upload(client, headers, sample_pdf(), title="…" * 301).status_code == 422
    monkeypatch.setattr(storage, "MAX_PDF_BYTES", 20)
    assert upload(client, headers, (b"abcde" for _ in range(5))).status_code == 413


def test_partial_storage_failure_keeps_no_card_and_supports_retry_and_cleanup(client, session, pdf_services, monkeypatch):
    headers = auth_headers(1)
    blobs, scanner = pdf_services
    data = sample_pdf()
    original_put = storage.put_pdf

    def uncertain_put(key, body):
        original_put(key, body)
        raise storage.PdfServiceUnavailable

    with monkeypatch.context() as failing:
        failing.setattr(storage, "put_pdf", uncertain_put)
        assert upload(client, headers, data).status_code == 503
    item = session.scalar(select(PdfObject))
    object_id = item.id
    assert item.creating and not item.published and item.id in blobs
    assert cleanup(session, now=datetime.now(timezone.utc)) == (0, 0)
    assert "pdf_attachments" not in client.get("/me/export", headers=headers).json()
    assert client.get("/contents", headers=headers).json()["total"] == 0

    scanner.response = b"stream: OK\0"
    material = upload(client, headers, data).json()
    assert material["title"] == "Спецификация"
    assert list(blobs) == [object_id]
    monkeypatch.setattr(storage, "MAX_PDF_COUNT", 1)
    scanner.response = b"stream: OK\0"
    assert upload(client, headers, sample_pdf(width=250)).json()["detail"]["code"] == "pdf_quota"
    assert client.delete(f"/contents/{material['id']}", headers=headers).status_code == 204
    session.expire_all()
    assert item.user_id is None and item.content_id is None and item.charged_user_id is not None

    def failed_delete(_key):
        raise storage.PdfServiceUnavailable

    with monkeypatch.context() as failing:
        failing.setattr(storage, "delete_pdf_object", failed_delete)
        assert cleanup(session, now=datetime.now(timezone.utc)) == (0, 1)
    assert object_id in blobs
    assert cleanup(session, now=datetime.now(timezone.utc)) == (1, 0)
    assert blobs == {}


def test_pending_cleanup_and_account_delete(client, session, pdf_services, monkeypatch):
    signup = client.post("/mobile/auth/register", json={
        "email": "pdf@example.com", "password": "synthetic-password", "consent": True,
    })
    headers = {"Authorization": "Bearer " + signup.json()["token"]}
    blobs, scanner = pdf_services
    material = upload(client, headers, sample_pdf()).json()
    assert material["content_type"] == "pdf"
    first_path = pdf_path(material)
    scanner.response = b"stream: OK\0"

    def fail_put(_key, _data):
        raise storage.PdfServiceUnavailable

    with monkeypatch.context() as failing:
        failing.setattr(storage, "put_pdf", fail_put)
        assert upload(client, headers, sample_pdf(width=300)).status_code == 503
    assert cleanup(session, now=datetime.now(timezone.utc)) == (0, 0)
    assert cleanup(session, now=datetime.now(timezone.utc) + timedelta(hours=2)) == (1, 0)
    assert client.get(first_path + "/download", headers=headers).status_code == 200
    assert client.post("/auth/delete-account", headers=headers, json={"password": "synthetic-password"}).status_code == 204
    assert client.get(first_path, headers=headers).status_code == 401
    session.expire_all()
    record = session.scalar(select(PdfObject))
    assert record.user_id is None and record.content_id is None and record.charged_user_id is None
    assert cleanup(session, now=datetime.now(timezone.utc)) == (1, 0)
    assert blobs == {}
