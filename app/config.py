from typing import Literal
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    # hide_input_in_errors: при ошибке настроек в сообщение не попадают значения
    # (пароль БД, токены, пароль почты)
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: str
    test_database_url: str = ""

    # Staging сохраняет HTTPS/Secure-cookie, но допускает приватный capture.
    # Production требует настоящий SMTP; console разрешён только в dev.
    app_env: Literal["dev", "staging", "prod"] = "dev"
    # Адрес сайта в браузере. Изменяющие запросы по cookie принимаются только
    # с этого origin. Открывать сайт нужно именно по этому адресу.
    app_origin: str = "http://localhost:8000"
    cookie_secure: bool = False

    # Секрет для подписи ссылок отписки (HMAC), не короче 32 символов.
    # Только в окружении. Смена ключа делает недействительными все выданные ссылки.
    secret_key: str = ""

    # console: только dev; smtp: отправка; capture: приватные MIME-файлы только staging.
    email_backend: Literal["console", "smtp", "capture"] = "console"
    capture_email_dir: Path = Path("/var/lib/teleiosis/captured-mail")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"

    @model_validator(mode="after")
    def check_web_settings(self):
        origin = self.app_origin.strip().lower().rstrip("/")
        parts = urlsplit(origin)
        if (
            parts.scheme not in ("http", "https")
            or not parts.netloc
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.path
            or parts.query
            or parts.fragment
        ):
            raise ValueError("APP_ORIGIN must look like https://example.com (no path)")
        self.app_origin = origin
        if self.app_env in ("prod", "staging"):
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true outside development")
            if parts.scheme != "https":
                raise ValueError("APP_ORIGIN must start with https:// outside development")
            if self.email_backend == "console" or (self.app_env == "prod" and self.email_backend != "smtp"):
                raise ValueError(
                    "EMAIL_BACKEND must be smtp when APP_ENV=prod "
                    "(console mode prints reset links)"
                )
            if self.email_backend == "smtp" and self.smtp_security == "none":
                raise ValueError("SMTP_SECURITY must be starttls or ssl when APP_ENV=prod")
            if len(self.secret_key) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters "
                    "when APP_ENV=prod"
                )
        if self.email_backend == "smtp" and not (self.smtp_host and self.smtp_from):
            raise ValueError("SMTP_HOST and SMTP_FROM are required when EMAIL_BACKEND=smtp")
        if self.email_backend == "capture":
            if self.app_env != "staging":
                raise ValueError("EMAIL_BACKEND=capture is only allowed in staging")
            if not self.capture_email_dir.is_absolute():
                raise ValueError("CAPTURE_EMAIL_DIR must be absolute")
        return self


settings = Settings()
