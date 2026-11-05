from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    bot_token: str = ""
    test_database_url: str = ""
    # Секретный ключ, которым бот представляется API (не короче 32 символов).
    # Если не задан или короткий, вход ботом отключён.
    bot_api_key: str = ""
    # Только для локальной разработки. На сервере должно быть false.
    dev_auth_enabled: bool = False


settings = Settings()