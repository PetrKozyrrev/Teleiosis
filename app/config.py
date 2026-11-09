from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # hide_input_in_errors: при ошибке настроек в сообщение не попадают значения
    # (пароль БД, токены, пароль почты)
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: str
    bot_token: str = ""
    test_database_url: str = ""
    # Секретный ключ, которым бот представляется API (не короче 32 символов).
    # Если не задан или короткий, вход ботом отключён.
    bot_api_key: str = ""

    # dev или prod. В prod обязательны HTTPS, Secure-cookie и настоящая почта.
    app_env: Literal["dev", "prod"] = "dev"
    # Адрес сайта в браузере. Изменяющие запросы по cookie принимаются только
    # с этого origin. Открывать сайт нужно именно по этому адресу.
    app_origin: str = "http://localhost:8000"
    cookie_secure: bool = False

    # Почта. console: письма печатаются в терминал (только для разработки,
    # в письмах есть ссылки с токенами). smtp: настоящая отправка.
    email_backend: Literal["console", "smtp"] = "console"
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
            or parts.path
            or parts.query
            or parts.fragment
        ):
            raise ValueError("APP_ORIGIN must look like https://example.com (no path)")
        self.app_origin = origin
        if self.app_env == "prod":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true when APP_ENV=prod")
            if parts.scheme != "https":
                raise ValueError("APP_ORIGIN must start with https:// when APP_ENV=prod")
            if self.email_backend != "smtp":
                raise ValueError(
                    "EMAIL_BACKEND must be smtp when APP_ENV=prod "
                    "(console mode prints reset links)"
                )
        if self.email_backend == "smtp" and not (self.smtp_host and self.smtp_from):
            raise ValueError("SMTP_HOST and SMTP_FROM are required when EMAIL_BACKEND=smtp")
        return self


settings = Settings()