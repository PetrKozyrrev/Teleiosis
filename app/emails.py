from email_validator import EmailNotValidError, validate_email

MAX_EMAIL_LENGTH = 254


def normalize_email(raw: str) -> str:
    """Проверяет адрес и приводит его к единому виду: без пробелов по краям,
    в нижнем регистре. Бросает ValueError, если адрес некорректен.

    DNS-проверка доставляемости выключена: она ходит в сеть и не нужна для входа.
    """
    try:
        info = validate_email(raw.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError("Invalid email address") from exc
    # Библиотека приводит к нижнему регистру домен, но не локальную часть.
    email = info.normalized.lower()
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValueError("Email is too long")
    return email