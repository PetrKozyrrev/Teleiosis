import logging

import pytest

import app.mailer as mailer
from app.config import settings


def test_console_backend_prints_the_email(capsys):
    mailer.send_email("a@example.com", "Тема", "Строка письма")
    out = capsys.readouterr().out
    assert "a@example.com" in out
    assert "Строка письма" in out


def test_password_reset_email_contains_the_link(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send_email", lambda *args: sent.append(args))
    link = "http://localhost:8000/app/reset.html#token=abc"
    mailer.send_password_reset("a@example.com", link)
    to, subject, body = sent[0]
    assert to == "a@example.com"
    assert subject
    assert link in body


class FakeSMTP:
    instances = []
    fail = False

    def __init__(self, host, port, timeout=None, context=None):
        self.args = (host, port, timeout)
        self.context = context
        self.calls = []
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        if FakeSMTP.fail:
            raise OSError("connection lost")
        self.message = message


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail = False
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.ru")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "secret-password")
    monkeypatch.setattr(settings, "smtp_from", "Teleiosis <noreply@example.ru>")
    monkeypatch.setattr(settings, "smtp_security", "starttls")
    return FakeSMTP


def test_smtp_starttls_flow(smtp):
    mailer.send_email("a@example.com", "Тема письма", "Текст письма")
    server = smtp.instances[0]
    assert server.args == ("smtp.example.ru", 587, mailer.SMTP_TIMEOUT)
    assert server.calls[:2] == ["starttls", ("login", "mailer", "secret-password")]
    assert server.message["To"] == "a@example.com"
    assert server.message["From"] == "Teleiosis <noreply@example.ru>"
    assert server.message["Subject"] == "Тема письма"
    assert "Текст письма" in server.message.get_content()


def test_smtp_ssl_skips_starttls(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_security", "ssl")
    mailer.send_email("a@example.com", "Тема", "Текст")
    assert "starttls" not in smtp.instances[0].calls


def test_no_login_without_user(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "")
    mailer.send_email("a@example.com", "Тема", "Текст")
    assert not any(isinstance(c, tuple) for c in smtp.instances[0].calls)


def test_send_failure_is_swallowed_and_not_leaking(smtp, caplog):
    smtp.fail = True
    with caplog.at_level(logging.ERROR):
        mailer.send_email("a@example.com", "Тема", "Секретный текст")
    assert "OSError" in caplog.text
    assert "a@example.com" not in caplog.text
    assert "Секретный текст" not in caplog.text



def test_verification_email_contains_the_link(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send_email", lambda *args: sent.append(args))
    link = "http://localhost:8000/app/verify.html#token=abc"
    mailer.send_email_verification("a@example.com", link)
    to, subject, body = sent[0]
    assert to == "a@example.com"
    assert subject
    assert link in body