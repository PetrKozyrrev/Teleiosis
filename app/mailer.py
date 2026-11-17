"""console для разработки, SMTP для доставки, приватный capture для staging."""

import logging
import smtplib
import ssl
import os
import stat
import tempfile
from pathlib import Path
from uuid import uuid4
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 10  # секунд


def capture_email(message: EmailMessage) -> None:
    """Closed staging mailbox: private atomic MIME files, never logs tokens."""
    if settings.app_env != "staging":
        raise ValueError("Mail capture requires staging")
    directory = settings.capture_email_dir
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise PermissionError("Capture directory must be private and owned by the process")
    # Refuse an overflowing test mailbox instead of silently losing old mail.
    if sum(1 for _ in directory.glob("*.eml")) >= 1000:
        raise OSError("Capture mailbox is full")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".pending-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(message.as_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(directory / f"{uuid4().hex}.eml")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def send_email(
    to: str, subject: str, body: str, headers: dict[str, str] | None = None
) -> bool:
    """Возвращает True, если письмо принято почтовым сервером (в режиме console
    всегда True). Никогда не бросает исключений: сбой почты не должен ломать запрос.
    В лог попадает только тип ошибки, без адреса и без текста письма.
    headers: дополнительные заголовки (например, List-Unsubscribe)."""
    extra = headers or {}

    if settings.email_backend == "console":
        extra_lines = "".join(f"{name}: {value}\n" for name, value in extra.items())
        print(
            "\n===== DEV EMAIL (EMAIL_BACKEND=console) =====\n"
            f"To: {to}\nSubject: {subject}\n{extra_lines}\n{body}\n"
            "=============================================\n",
            flush=True,
        )
        return True

    try:
        message = EmailMessage()
        message["From"] = settings.smtp_from or "Teleiosis staging <noreply@example.invalid>"
        message["To"] = to
        message["Subject"] = subject
        for name, value in extra.items():
            message[name] = value  # перевод строки в значении даст ValueError
        message.set_content(body)

        if settings.email_backend == "capture":
            capture_email(message)
            return True

        context = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            server = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT, context=context
            )
        else:
            server = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT
            )
        with server:
            if settings.smtp_security == "starttls":
                server.starttls(context=context)
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except Exception as exc:  # намеренно широко: почта не должна ломать запрос
        logger.error("email send failed: %s", type(exc).__name__)
        return False
    return True


def send_password_reset(to: str, link: str) -> bool:
    return send_email(
        to,
        "Teleiosis: восстановление доступа",
        "Вы (или кто-то другой) запросили сброс пароля для аккаунта Teleiosis.\n\n"
        "Чтобы задать новый пароль, откройте ссылку. Она действует 1 час и "
        "работает один раз:\n"
        f"{link}\n\n"
        "Если вы ничего не запрашивали, просто проигнорируйте это письмо: "
        "пароль не изменится.",
    )


def send_email_verification(to: str, link: str) -> bool:
    return send_email(
        to,
        "Teleiosis: подтверждение e-mail",
        "Этот адрес указан при регистрации в Teleiosis.\n\n"
        "Чтобы подтвердить e-mail и получать напоминания, откройте ссылку. "
        "Она действует 24 часа и работает один раз:\n"
        f"{link}\n\n"
        "Если вы не регистрировались, просто проигнорируйте это письмо.",
    )
