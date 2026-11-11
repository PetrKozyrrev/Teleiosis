"""Отправка писем. Режим console печатает письмо в терминал (разработка),
режим smtp отправляет через почтовый сервер."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 10  # секунд


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
        message["From"] = settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        for name, value in extra.items():
            message[name] = value  # перевод строки в значении даст ValueError
        message.set_content(body)

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