import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from typing import get_args

from app.schemas import ContentSource, ContentStatus, SortOrder

WEB = Path(__file__).resolve().parent.parent / "web"
PAGES = [
    "index.html", "login.html", "register.html", "forgot.html", "reset.html",
    "item.html", "categories.html", "add.html", "bookmark.html", "verify.html",
    "settings.html", "progress.html",
]
HTML_FILES = sorted(WEB.glob("*.html"))
JS_FILES = sorted((WEB / "js").glob("*.js"))

DANGEROUS_JS = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]


def local(reference):
    return not re.match(r"([a-z]+:|//)", reference)


def test_expected_pages_exist():
    assert set(PAGES) <= {p.name for p in HTML_FILES}


@pytest.mark.parametrize("page", PAGES)
def test_page_served_with_security_headers(client, page):
    response = client.get(f"/app/{page}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    policy = response.headers["content-security-policy"]
    for part in ("default-src 'self'", "img-src 'self' data:", "object-src 'none'", "frame-ancestors 'none'"):
        assert part in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-cache"


def test_site_root_serves_the_library_page(client):
    response = client.get("/app/")
    assert response.status_code == 200
    assert "Библиотека" in response.text


def test_redirects_to_the_site(client):
    root = client.get("/", follow_redirects=False)
    assert root.status_code in (302, 307)
    assert root.headers["location"].endswith("/app/")
    bare = client.get("/app", follow_redirects=False)
    assert bare.status_code in (301, 307)
    assert bare.headers["location"].endswith("/app/")


def test_missing_file_is_404_but_keeps_headers(client):
    response = client.get("/app/nope.html")
    assert response.status_code == 404
    assert "content-security-policy" in response.headers


def test_path_traversal_is_not_possible(client):
    assert client.get("/app/..%2f..%2fapp%2fmain.py").status_code == 404
    assert client.get("/app/%2e%2e/%2e%2e/.env").status_code == 404


def test_api_and_docs_do_not_get_site_headers(client):
    for path in ("/health", "/docs"):
        assert "content-security-policy" not in client.get(path).headers


@pytest.mark.parametrize("page", HTML_FILES, ids=lambda p: p.name)
def test_html_references_resolve(client, page):
    html = page.read_text(encoding="utf-8")
    references = [r for r in re.findall(r'(?:src|href)="([^"#?]+)', html) if local(r)]
    assert references
    for reference in references:
        url = urljoin("/app/", reference)
        assert client.get(url).status_code == 200, f"{page.name}: {reference}"


@pytest.mark.parametrize("script", JS_FILES, ids=lambda p: p.name)
def test_js_imports_resolve(client, script):
    text = script.read_text(encoding="utf-8")
    for reference in re.findall(r'from\s+"(\.[^"]+)"', text):
        url = urljoin("/app/js/", reference)
        assert client.get(url).status_code == 200, f"{script.name}: {reference}"


@pytest.mark.parametrize("page", HTML_FILES, ids=lambda p: p.name)
def test_no_inline_code_that_csp_would_block(page):
    html = page.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html
    assert not re.search(r"\sstyle\s*=", html)
    assert not re.search(r"\son[a-z]+\s*=", html, re.I)


@pytest.mark.parametrize("page", HTML_FILES, ids=lambda p: p.name)
def test_forms_never_submit_passwords_to_the_address_bar(page):
    html = (WEB / page.name).read_text(encoding="utf-8")
    for form in re.findall(r"<form\b[^>]*>", html):
        assert 'method="post"' in form or 'method="dialog"' in form


@pytest.mark.parametrize("script", JS_FILES, ids=lambda p: p.name)
def test_js_does_not_use_dangerous_apis(script):
    text = script.read_text(encoding="utf-8")
    for api in DANGEROUS_JS:
        assert api not in text, f"{script.name}: {api}"

def test_source_icons_used_by_cards_exist(client):
    cards = (WEB / "js" / "cards.js").read_text(encoding="utf-8")
    icons = re.findall(r'"(img/source-[a-z]+\.svg)"', cards)
    assert len(icons) == len(get_args(ContentSource))
    for icon in icons:
        response = client.get(urljoin("/app/", icon))
        assert response.status_code == 200, icon
        assert response.headers["content-type"].startswith("image/svg+xml")


def test_filters_and_labels_match_the_api():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    cards = (WEB / "js" / "cards.js").read_text(encoding="utf-8")
    values = get_args(ContentStatus) + get_args(ContentSource) + get_args(SortOrder)
    for value in values:
        assert f'value="{value}"' in html, value
    for value in get_args(ContentStatus) + get_args(ContentSource):
        assert re.search(rf"\b{value}:", cards), value

AUTH_PAGES = ["index.html", "item.html", "categories.html", "add.html", "bookmark.html", "settings.html", "progress.html"]
NAV_PAGES = ["index.html", "item.html", "categories.html", "bookmark.html", "settings.html", "progress.html"]


@pytest.mark.parametrize("page", AUTH_PAGES)
def test_authenticated_pages_have_the_load_guard(page):
    html = (WEB / page).read_text(encoding="utf-8")
    assert 'src="js/boot.js"' in html
    assert 'id="boot-error"' in html


@pytest.mark.parametrize("script", ["index.js", "item.js", "categories.js", "add.js", "bookmark.js", "settings.js", "progress.js"])
def test_page_scripts_mark_themselves_ready(script):
    assert "markReady()" in (WEB / "js" / script).read_text(encoding="utf-8")


@pytest.mark.parametrize("script", ["library.js", "item.js"])
def test_pages_track_opening_of_the_original(script):
    assert "bindOpenTracking(" in (WEB / "js" / script).read_text(encoding="utf-8")

@pytest.mark.parametrize("page", NAV_PAGES)
def test_authenticated_pages_have_navigation(page):
    html = (WEB / page).read_text(encoding="utf-8")
    assert 'class="topnav"' in html
    assert 'href="categories.html"' in html
    assert 'href="./"' in html
    assert 'href="settings.html"' in html
    assert 'href="progress.html"' in html


def test_library_reads_the_category_from_the_address():
    text = (WEB / "js" / "library.js").read_text(encoding="utf-8")
    assert 'get("category")' in text


def test_category_links_match_what_the_library_reads():
    text = (WEB / "js" / "categories.js").read_text(encoding="utf-8")
    assert "./?category=" in text

def test_library_links_to_the_bookmark_page():
    assert 'href="bookmark.html"' in (WEB / "index.html").read_text(encoding="utf-8")


def test_bookmarklet_opens_the_add_page_safely():
    bookmark = (WEB / "js" / "bookmark.js").read_text(encoding="utf-8")
    assert "/app/add.html" in bookmark
    assert "#url=" in bookmark
    assert "noopener" in bookmark


def test_add_page_reads_the_fragment_and_never_saves_by_itself():
    add = (WEB / "js" / "add.js").read_text(encoding="utf-8")
    assert "location.hash" in add
    assert "location.search" not in add
    assert "requestSubmit" not in add
    assert ".submit()" not in add




def test_verify_page_confirms_by_post_and_hides_the_token():
    text = (WEB / "js" / "verify.js").read_text(encoding="utf-8")
    assert "/auth/email-verification/confirm" in text
    assert "replaceState" in text
    assert "location.search" not in text.replace("location.pathname + location.search", "")


def test_topbar_offers_to_verify_the_email():
    text = (WEB / "js" / "session.js").read_text(encoding="utf-8")
    assert "/auth/email-verification/request" in text

from app.timezones import is_valid_timezone


def test_settings_zone_list_has_only_zones_the_server_accepts():
    text = (WEB / "js" / "settings.js").read_text(encoding="utf-8")
    zones = re.findall(r'\["([A-Za-z_]+(?:/[A-Za-z_]+)?)",', text)
    assert len(zones) >= 10
    for zone in zones:
        assert is_valid_timezone(zone), zone


def test_settings_page_talks_to_the_right_endpoints():
    text = (WEB / "js" / "settings.js").read_text(encoding="utf-8")
    assert '"/me/settings"' in text
    assert '"/auth/change-password"' in text



def test_progress_page_uses_native_progress_elements():
    html = (WEB / "progress.html").read_text(encoding="utf-8")
    assert html.count("<progress") == 2
    assert "<table" in html


def test_stats_module_calls_the_stats_endpoint():
    assert '"/stats"' in (WEB / "js" / "stats.js").read_text(encoding="utf-8")


def test_library_shows_the_stats_strip():
    assert 'id="stats-strip"' in (WEB / "index.html").read_text(encoding="utf-8")
    assert "loadStats" in (WEB / "js" / "index.js").read_text(encoding="utf-8")