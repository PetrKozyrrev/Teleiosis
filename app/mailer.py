"""Отправка писем. Режим console печатает письмо в терминал (разработка),
режим smtp отправляет через почтовый сервер."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 10  # секунд


def send_email(to: str, subject: str, body: str) -> None:
    """Никогда не бросает исключений: сбой почты не должен ломать запрос.
    В лог попадает только тип ошибки, без адреса и без текста письма."""
    if settings.email_backend == "console":
        print(
            "\n===== DEV EMAIL (EMAIL_BACKEND=console) =====\n"
            f"To: {to}\nSubject: {subject}\n\n{body}\n"
            "=============================================\n",
            flush=True,
        )
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    try:
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


def send_password_reset(to: str, link: str) -> None:
    send_email(
        to,
        "Teleiosis: восстановление доступа",
        "Вы (или кто-то другой) запросили сброс пароля для аккаунта Teleiosis.\n\n"
        "Чтобы задать новый пароль, откройте ссылку. Она действует 1 час и "
        "работает один раз:\n"
        f"{link}\n\n"
        "Если вы ничего не запрашивали, просто проигнорируйте это письмо: "
        "пароль не изменится.",
    )