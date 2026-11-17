from email import policy
from email.parser import BytesParser
import logging
import os

import pytest

from app.config import settings
from app.mailer import send_email


@pytest.fixture
def capture(tmp_path, monkeypatch):
    directory = tmp_path / "mail"
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "email_backend", "capture")
    monkeypatch.setattr(settings, "capture_email_dir", directory)
    monkeypatch.setattr(settings, "smtp_from", "")
    # Capture must not even construct a network SMTP connection.
    def forbidden(*args, **kwargs):
        pytest.fail("Capture attempted an SMTP connection")
    monkeypatch.setattr("app.mailer.smtplib.SMTP", forbidden)
    monkeypatch.setattr("app.mailer.smtplib.SMTP_SSL", forbidden)
    return directory


def test_capture_is_private_complete_mime_and_never_printed(capture, capsys, caplog):
    token = "secret-one-time-reset-link"
    assert send_email("test@example.com", "Проверка", token, {"X-Test": "captured"}) is True
    assert capture.stat().st_mode & 0o777 == 0o700
    files = list(capture.iterdir())
    assert len(files) == 1 and files[0].suffix == ".eml"
    assert files[0].stat().st_mode & 0o777 == 0o600
    message = BytesParser(policy=policy.default).parsebytes(files[0].read_bytes())
    assert message["To"] == "test@example.com"
    assert message["X-Test"] == "captured"
    assert token in message.get_content()
    assert token not in capsys.readouterr().out + caplog.text


@pytest.mark.parametrize("unsafe", ["permissions", "symlink", "production"])
def test_capture_rejects_unsafe_destination_or_environment(capture, monkeypatch, unsafe, caplog):
    if unsafe == "permissions":
        capture.mkdir(mode=0o755)
    elif unsafe == "symlink":
        target = capture.parent / "elsewhere"
        target.mkdir(mode=0o700)
        capture.symlink_to(target, target_is_directory=True)
    else:
        monkeypatch.setattr(settings, "app_env", "prod")
    with caplog.at_level(logging.ERROR):
        assert send_email("private@example.com", "Тема", "private-token") is False
    assert "private-token" not in caplog.text and "private@example.com" not in caplog.text
    assert not list(capture.glob("*.eml"))


def test_capture_disk_failure_does_not_publish_partial_message(capture, monkeypatch):
    def fail(*args):
        raise OSError("disk error")
    monkeypatch.setattr(os, "fsync", fail)
    assert send_email("test@example.com", "Тема", "secret") is False
    assert list(capture.iterdir()) == []


def test_capture_never_overwrites_another_message(capture):
    for value in ("first", "second"):
        assert send_email("test@example.com", "Тема", value) is True
    files = list(capture.glob("*.eml"))
    assert len(files) == 2
    assert {BytesParser(policy=policy.default).parsebytes(p.read_bytes()).get_content().strip() for p in files} == {"first", "second"}
