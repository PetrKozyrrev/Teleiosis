from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    bot_token: str = ""
    test_database_url: str = ""
    # Секретный ключ, которым бот представляется API (не короче 32 символов).
    # Если не задан или короткий, вход ботом отключён.
    bot_api_key: str = ""

    # dev или prod. В prod обязательны HTTPS и Secure-cookie.
    app_env: Literal["dev", "prod"] = "dev"
    # Адрес сайта в браузере. Изменяющие запросы по cookie принимаются только
    # с этого origin. Открывать сайт нужно именно по этому адресу.
    app_origin: str = "http://localhost:8000"
    cookie_secure: bool = False

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
        return self


settings = Settings()