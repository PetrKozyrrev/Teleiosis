import asyncio

import httpx2
import pytest

from bot.api import ApiClient, ApiError


def call(handler, telegram_id=42, username=None):
    async def run():
        client = ApiClient(
            "http://api.test", "secret-key", transport=httpx2.MockTransport(handler)
        )
        try:
            return await client.register(telegram_id, username)
        finally:
            await client.close()

    return asyncio.run(run())


def test_register_sends_auth_headers():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["path"] = request.url.path
        return httpx2.Response(200, json={"id": 1})

    assert call(handler, 42, "ivan") == {"id": 1}
    assert seen["path"] == "/me"
    assert seen["headers"]["x-bot-key"] == "secret-key"
    assert seen["headers"]["x-telegram-id"] == "42"
    assert seen["headers"]["x-telegram-username"] == "ivan"


def test_username_header_omitted_when_missing():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        return httpx2.Response(200, json={})

    call(handler, 42, None)
    assert "x-telegram-username" not in seen["headers"]


def test_error_status_raises_api_error():
    with pytest.raises(ApiError):
        call(lambda request: httpx2.Response(401))


def test_network_error_raises_api_error():
    def handler(request):
        raise httpx2.ConnectError("boom")

    with pytest.raises(ApiError):
        call(handler)