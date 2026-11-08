import pytest

from app.emails import normalize_email


def test_normalize_trims_and_lowercases():
    assert normalize_email("  Ivan@Example.COM ") == "ivan@example.com"


def test_plus_tag_is_kept():
    assert normalize_email("Ivan+news@example.com") == "ivan+news@example.com"


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "plain", "a@", "@example.com", "a b@example.com", "a@@example.com"],
)
def test_invalid_emails_rejected(raw):
    with pytest.raises(ValueError):
        normalize_email(raw)