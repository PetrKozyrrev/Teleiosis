import pytest

from app.urls import InvalidUrl, clean_url, detect_source, normalize_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "https://www.Example.com/Path/?utm_source=x&b=2&a=1#frag",
            "https://example.com/Path?a=1&b=2",
        ),
        ("http://example.com/", "https://example.com"),
        ("example.com/a", "https://example.com/a"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("https://youtu.be/dQw4w9WgXcQ?si=abc&t=10", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share&t=5",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://t.me/durov/123?single", "https://t.me/durov/123"),
        ("https://telegram.me/durov/123", "https://t.me/durov/123"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "https://localhost/x",
        "https://user:pass@example.com",
        "http://",
        "has space.com",
    ],
)
def test_invalid_urls(raw):
    with pytest.raises(InvalidUrl):
        clean_url(raw)


def test_detect_source():
    assert detect_source("https://youtu.be/dQw4w9WgXcQ") == ("youtube", "video")
    assert detect_source("https://t.me/durov/123") == ("telegram", "post")
    assert detect_source("https://example.com/post") == ("web", "article")