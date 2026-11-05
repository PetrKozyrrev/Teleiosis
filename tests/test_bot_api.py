import asyncio
import json

import httpx2
import pytest

from bot.api import ApiClient, ApiError


def run(handler, method, *args):
    async def go():
        client = ApiClient(
            "http://api.test", "secret-key", transport=httpx2.MockTransport(handler)
        )
        try:
            return await getattr(client, method)(*args)
        finally:
            await client.close()

    return asyncio.run(go())


def test_register_sends_auth_headers():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["path"] = request.url.path
        return httpx2.Response(200, json={"id": 1})

    assert run(handler, "register", 42, "ivan") == {"id": 1}
    assert seen["path"] == "/me"
    assert seen["headers"]["x-bot-key"] == "secret-key"
    assert seen["headers"]["x-telegram-id"] == "42"
    assert seen["headers"]["x-telegram-username"] == "ivan"


def test_username_header_omitted_when_missing():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        return httpx2.Response(200, json={})

    run(handler, "register", 42, None)
    assert "x-telegram-username" not in seen["headers"]


def test_error_status_raises_api_error():
    with pytest.raises(ApiError):
        run(lambda request: httpx2.Response(401), "register", 42, None)


def test_network_error_raises_api_error():
    def handler(request):
        raise httpx2.ConnectError("boom")

    with pytest.raises(ApiError):
        run(handler, "register", 42, None)


def test_save_url_saved():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx2.Response(201, json={"id": 7, "title": "Видео"})

    result = run(handler, "save_url", 42, None, "https://example.com/a")
    assert result.status == "saved"
    assert result.content["title"] == "Видео"
    assert (seen["method"], seen["path"]) == ("POST", "/contents")
    assert seen["body"] == {"url": "https://example.com/a"}


def test_save_url_duplicate_has_existing_id():
    def handler(request):
        return httpx2.Response(
            409, json={"detail": {"message": "Already saved", "existing_id": 5}}
        )

    result = run(handler, "save_url", 42, None, "https://example.com/a")
    assert result.status == "duplicate"
    assert result.existing_id == 5


def test_save_url_duplicate_with_unexpected_body():
    result = run(lambda request: httpx2.Response(409, text="oops"), "save_url", 42, None, "x.com")
    assert result.status == "duplicate"
    assert result.existing_id is None


def test_save_url_invalid():
    result = run(lambda request: httpx2.Response(422, json={}), "save_url", 42, None, "bad")
    assert result.status == "invalid"


def test_save_url_server_error_raises():
    with pytest.raises(ApiError):
        run(lambda request: httpx2.Response(500), "save_url", 42, None, "https://example.com")


def test_get_content_ok_and_not_found():
    assert run(lambda r: httpx2.Response(200, json={"title": "T"}), "get_content", 42, None, 1) == {"title": "T"}
    assert run(lambda r: httpx2.Response(404), "get_content", 42, None, 1) is None


def test_get_content_network_error_returns_none():
    def handler(request):
        raise httpx2.ConnectError("boom")

    assert run(handler, "get_content", 42, None, 1) is None

def test_save_url_with_title_and_note():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(201, json={"id": 1, "title": "T"})

    result = run(
        handler, "save_url", 42, None, "https://t.me/durov/1", "Заголовок", "Текст поста"
    )
    assert result.status == "saved"
    assert seen["body"] == {
        "url": "https://t.me/durov/1",
        "title": "Заголовок",
        "note": "Текст поста",
    }


def test_save_note_sends_only_note():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["path"] = request.url.path
        return httpx2.Response(201, json={"id": 2, "title": "Идея", "content_type": "note"})

    result = run(handler, "save_note", 42, None, "Идея про рассылку")
    assert result.status == "saved"
    assert seen["path"] == "/contents"
    assert seen["body"] == {"note": "Идея про рассылку"}


def test_save_note_invalid():
    result = run(lambda r: httpx2.Response(422, json={}), "save_note", 42, None, "x")
    assert result.status == "invalid"

def test_update_content_sends_patch_and_returns_content():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={"id": 5, "status": "studied"})

    result = run(handler, "update_content", 42, None, 5, {"status": "studied"})
    assert result == {"id": 5, "status": "studied"}
    assert (seen["method"], seen["path"]) == ("PATCH", "/contents/5")
    assert seen["body"] == {"status": "studied"}


def test_update_content_can_clear_category():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={"id": 5})

    run(handler, "update_content", 42, None, 5, {"category_id": None})
    assert seen["body"] == {"category_id": None}


def test_update_content_not_found_returns_none():
    assert run(lambda r: httpx2.Response(404), "update_content", 42, None, 5, {"status": "planned"}) is None


def test_update_content_other_error_raises():
    with pytest.raises(ApiError):
        run(lambda r: httpx2.Response(500), "update_content", 42, None, 5, {"status": "planned"})


def test_list_categories():
    result = run(lambda r: httpx2.Response(200, json=[{"id": 1, "name": "Бизнес"}]), "list_categories", 42, None)
    assert result == [{"id": 1, "name": "Бизнес"}]
    with pytest.raises(ApiError):
        run(lambda r: httpx2.Response(401), "list_categories", 42, None)


def test_create_category_results():
    created = run(lambda r: httpx2.Response(201, json={"id": 1, "name": "Бизнес"}), "create_category", 42, None, "Бизнес")
    assert created.status == "created"
    assert created.category["name"] == "Бизнес"
    assert run(lambda r: httpx2.Response(409), "create_category", 42, None, "Бизнес").status == "duplicate"
    assert run(lambda r: httpx2.Response(422), "create_category", 42, None, "").status == "invalid"
    with pytest.raises(ApiError):
        run(lambda r: httpx2.Response(500), "create_category", 42, None, "Бизнес")