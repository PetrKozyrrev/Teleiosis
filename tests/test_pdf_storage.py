from uuid import uuid4

import pytest

from app import pdf_storage
from app.config import settings


def test_private_storage_atomic_write_read_and_repeated_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pdf_local_dir", tmp_path)
    key = uuid4()
    target, partial = pdf_storage.local_paths(key)
    partial.write_bytes(b"unfinished")
    pdf_storage.put_pdf(key, b"pdf")
    assert not partial.exists()
    assert target.stat().st_mode & 0o777 == 0o600
    assert pdf_storage.get_pdf(key, 3) == b"pdf"
    with pytest.raises(pdf_storage.PdfServiceUnavailable):
        pdf_storage.get_pdf(key, 2)
    pdf_storage.delete_pdf_object(key)
    pdf_storage.delete_pdf_object(key)
    assert not target.exists()


def test_private_storage_capacity_keeps_existing_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pdf_local_dir", tmp_path)
    monkeypatch.setattr(pdf_storage, "LOCAL_STORE_LIMIT", 5)
    key = uuid4()
    pdf_storage.put_pdf(key, b"first")
    pdf_storage.put_pdf(key, b"again")
    for object_id in (key, uuid4()):
        with pytest.raises(pdf_storage.PdfServiceUnavailable):
            pdf_storage.put_pdf(object_id, b"larger")
    assert pdf_storage.get_pdf(key, 5) == b"again"
    assert not list(tmp_path.glob("*.part"))


def test_scanner_can_connect_over_private_unix_socket(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    path = tmp_path / "clamd.sock"
    monkeypatch.setattr(settings, "pdf_scanner_socket", path)
    sockets = MagicMock()
    connection = sockets.return_value.__enter__.return_value
    monkeypatch.setattr(pdf_storage.socket, "socket", sockets)

    with pdf_storage.scanner_connection() as actual:
        assert actual is connection
    sockets.assert_called_once_with(pdf_storage.socket.AF_UNIX, pdf_storage.socket.SOCK_STREAM)
    connection.settimeout.assert_called_once_with(8)
    connection.connect.assert_called_once_with(str(path))
