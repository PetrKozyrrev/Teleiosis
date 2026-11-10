"""Проверка названий часовых поясов (IANA, например Europe/Moscow).

Набор доступных зон считается один раз: функция available_timezones()
открывает много файлов. Нужен установленный tzdata (есть в requirements.txt).
"""

from functools import cache
from zoneinfo import ZoneInfo, available_timezones


@cache
def _known() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(name: object) -> bool:
    """True, только если это строка с названием существующей зоны."""
    if not isinstance(name, str) or name not in _known():
        return False
    try:
        ZoneInfo(name)  # данные зоны реально читаются
    except (ValueError, OSError, KeyError):
        return False
    return True