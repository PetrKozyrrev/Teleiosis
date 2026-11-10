import pytest

from app.timezones import is_valid_timezone


@pytest.mark.parametrize("name", ["UTC", "Europe/Moscow", "Asia/Vladivostok", "America/New_York"])
def test_known_zones(name):
    assert is_valid_timezone(name) is True


@pytest.mark.parametrize(
    "name",
    ["", "Moscow", "Europe/Nowhere", "../etc/passwd", " Europe/Moscow", "europe/moscow", None, 5],
)
def test_unknown_zones(name):
    assert is_valid_timezone(name) is False