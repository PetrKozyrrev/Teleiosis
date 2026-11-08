import pytest
from pydantic import ValidationError

from app.config import Settings

BASE = {"database_url": "postgresql+psycopg://u:p@localhost/db"}


def make(**kwargs):
    # _env_file=None: тест не зависит от настоящего .env
    return Settings(_env_file=None, **BASE, **kwargs)


def test_defaults_are_for_development():
    settings = make()
    assert settings.app_env == "dev"
    assert settings.app_origin == "http://localhost:8000"
    assert settings.cookie_secure is False


def test_origin_is_normalized():
    assert make(app_origin=" HTTP://LocalHost:8000/ ").app_origin == "http://localhost:8000"


@pytest.mark.parametrize(
    "origin", ["", "localhost:8000", "ftp://example.com", "https://example.com/path"]
)
def test_bad_origin_rejected(origin):
    with pytest.raises(ValidationError):
        make(app_origin=origin)


def test_prod_requires_secure_cookie():
    with pytest.raises(ValidationError):
        make(app_env="prod", app_origin="https://example.ru", cookie_secure=False)


def test_prod_requires_https_origin():
    with pytest.raises(ValidationError):
        make(app_env="prod", app_origin="http://example.ru", cookie_secure=True)


def test_prod_with_secure_settings_is_ok():
    settings = make(app_env="prod", app_origin="https://example.ru/", cookie_secure=True)
    assert settings.app_origin == "https://example.ru"