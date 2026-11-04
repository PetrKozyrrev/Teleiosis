import httpx2
import pytest

from app import metadata
from app.metadata import MAX_REDIRECTS, UnsafeUrl, ensure_public, fetch_metadata

PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """По умолчанию любой хост «резолвится» в публичный адрес."""
    monkeypatch.setattr(metadata, "resolve_ips", lambda host, port: [PUBLIC_IP])


def page(body, content_type="text/html; charset=utf-8", status=200):
    if isinstance(body, str):
        body = body.encode("utf-8")

    def handler(request):
        return httpx2.Response(
            status, headers={"content-type": content_type}, content=body
        )

    return httpx2.MockTransport(handler)


# ---------- защита от SSRF ----------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "172.16.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1%eth0",
        "::ffff:127.0.0.1",
        "fc00::1",
    ],
)
def test_non_public_addresses_blocked(monkeypatch, address):
    monkeypatch.setattr(metadata, "resolve_ips", lambda host, port: [address])
    with pytest.raises(UnsafeUrl):
        ensure_public("https://example.com/")


def test_mixed_addresses_blocked(monkeypatch):
    monkeypatch.setattr(
        metadata, "resolve_ips", lambda host, port: [PUBLIC_IP, "10.0.0.1"]
    )
    with pytest.raises(UnsafeUrl):
        ensure_public("https://example.com/")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https://example.com:8080/",
        "http://example.com:22/",
    ],
)
def test_bad_schemes_and_ports_blocked(url):
    with pytest.raises(UnsafeUrl):
        ensure_public(url)


def test_standard_ports_allowed():
    ensure_public("https://example.com/")
    ensure_public("http://example.com:80/")
    ensure_public("https://example.com:443/")


def test_dns_failure_blocked(monkeypatch):
    def boom(host, port):
        raise OSError("no such host")

    monkeypatch.setattr(metadata, "resolve_ips", boom)
    with pytest.raises(UnsafeUrl):
        ensure_public("https://example.com/")


def test_private_start_url_is_never_requested(monkeypatch):
    monkeypatch.setattr(metadata, "resolve_ips", lambda host, port: ["127.0.0.1"])
    requested = []

    def handler(request):
        requested.append(request.url.host)
        return httpx2.Response(200, headers={"content-type": "text/html"}, content=b"x")

    result = fetch_metadata(
        "https://example.com/", transport=httpx2.MockTransport(handler)
    )
    assert result is None
    assert requested == []


def test_redirect_to_private_address_is_blocked(monkeypatch):
    monkeypatch.setattr(
        metadata,
        "resolve_ips",
        lambda host, port: ["10.0.0.1"] if host == "internal.example" else [PUBLIC_IP],
    )
    requested = []

    def handler(request):
        requested.append(request.url.host)
        if request.url.host == "example.com":
            return httpx2.Response(
                302, headers={"location": "http://internal.example/secret"}
            )
        return httpx2.Response(
            200, headers={"content-type": "text/html"}, content=b"<title>secret</title>"
        )

    result = fetch_metadata(
        "https://example.com/", transport=httpx2.MockTransport(handler)
    )
    assert result is None
    assert requested == ["example.com"]


def test_redirect_to_public_address_is_followed():
    def handler(request):
        if request.url.host == "example.com":
            return httpx2.Response(
                302, headers={"location": "https://www.example.org/x"}
            )
        return httpx2.Response(
            200, headers={"content-type": "text/html"}, content=b"<title>Final</title>"
        )

    result = fetch_metadata(
        "https://example.com/", transport=httpx2.MockTransport(handler)
    )
    assert result.title == "Final"


def test_too_many_redirects():
    requests = []

    def handler(request):
        requests.append(1)
        return httpx2.Response(302, headers={"location": "https://example.com/loop"})

    result = fetch_metadata(
        "https://example.com/", transport=httpx2.MockTransport(handler)
    )
    assert result is None
    assert len(requests) == MAX_REDIRECTS + 1


# ---------- разбор страницы ----------


def test_open_graph_tags():
    html = """<html><head><title>Fallback</title>
    <meta property="og:title" content="  OG   Title ">
    <meta property="og:description" content="Описание">
    <meta property="og:image" content="/img/cover.png">
    </head><body></body></html>"""
    result = fetch_metadata("https://example.com/post", transport=page(html))
    assert result.title == "OG Title"
    assert result.description == "Описание"
    assert result.image_url == "https://example.com/img/cover.png"


def test_title_tag_fallback():
    html = "<head><title>Просто заголовок</title></head><body>текст</body>"
    result = fetch_metadata("https://example.com/", transport=page(html))
    assert result.title == "Просто заголовок"
    assert result.description is None
    assert result.image_url is None


def test_meta_after_head_is_ignored():
    html = (
        "<head><title>Real</title></head>"
        "<body><meta property='og:title' content='Fake'></body>"
    )
    result = fetch_metadata("https://example.com/", transport=page(html))
    assert result.title == "Real"


def test_long_title_truncated():
    html = f"<head><title>{'a' * 500}</title></head>"
    result = fetch_metadata("https://example.com/", transport=page(html))
    assert len(result.title) == 300


@pytest.mark.parametrize("image", ["javascript:alert(1)", "data:image/png;base64,AAAA"])
def test_unsafe_image_scheme_dropped(image):
    html = f'<head><title>T</title><meta property="og:image" content="{image}"></head>'
    result = fetch_metadata("https://example.com/", transport=page(html))
    assert result.title == "T"
    assert result.image_url is None


def test_windows_1251_page():
    html = "<head><title>Привет</title></head>"
    transport = page(html.encode("cp1251"), "text/html; charset=windows-1251")
    assert fetch_metadata("https://example.com/", transport=transport).title == "Привет"


def test_non_html_ignored():
    assert fetch_metadata(
        "https://example.com/file", transport=page("%PDF-1.4", "application/pdf")
    ) is None


def test_http_error_ignored():
    assert fetch_metadata(
        "https://example.com/", transport=page("<title>x</title>", status=404)
    ) is None


def test_large_page_is_truncated_not_fatal():
    body = b"<title>T</title>" + b"x" * 2_000_000
    result = fetch_metadata("https://example.com/", transport=page(body))
    assert result.title == "T"


def test_network_error_is_swallowed():
    def handler(request):
        raise httpx2.ConnectError("boom")

    assert fetch_metadata(
        "https://example.com/", transport=httpx2.MockTransport(handler)
    ) is None


# ---------- YouTube ----------


def test_youtube_uses_oembed():
    def handler(request):
        assert request.url.path == "/oembed"
        return httpx2.Response(
            200,
            json={
                "title": "Never Gonna Give You Up",
                "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            },
        )

    result = fetch_metadata(
        "https://youtu.be/dQw4w9WgXcQ", transport=httpx2.MockTransport(handler)
    )
    assert result.title == "Never Gonna Give You Up"
    assert result.image_url.startswith("https://i.ytimg.com/")


def test_youtube_error_returns_none():
    def handler(request):
        return httpx2.Response(404)

    assert fetch_metadata(
        "https://youtu.be/dQw4w9WgXcQ", transport=httpx2.MockTransport(handler)
    ) is None