from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    """Настройки бота. База данных боту не нужна."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    bot_api_key: str = ""
    api_base_url: str = "http://127.0.0.1:8000"
    # Прокси только для запросов к Telegram. Пусто = напрямую.
    telegram_proxy: str = ""


settings = BotSettings()