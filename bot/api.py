from dataclasses import dataclass

import httpx2


class ApiError(Exception):
    """API недоступен или вернул ошибку. Текст не содержит секретов."""


@dataclass
class SaveResult:
    status: str  # "saved", "duplicate" или "invalid"
    content: dict | None = None  # для "saved"
    existing_id: int | None = None  # для "duplicate"


def _existing_id(response) -> int | None:
    try:
        value = response.json()["detail"]["existing_id"]
    except (ValueError, KeyError, TypeError):
        return None
    return value if isinstance(value, int) else None


class ApiClient:
    def __init__(self, base_url: str, bot_key: str, *, transport=None):
        # transport нужен только тестам
        self._client = httpx2.AsyncClient(
            base_url=base_url,
            timeout=httpx2.Timeout(15.0, connect=5.0),
            transport=transport,
            trust_env=False,
        )
        self._bot_key = bot_key

    def _headers(self, telegram_id: int, username: str | None) -> dict[str, str]:
        headers = {"X-Bot-Key": self._bot_key, "X-Telegram-Id": str(telegram_id)}
        if username:
            headers["X-Telegram-Username"] = username
        return headers

    async def _request(
        self, method: str, path: str, telegram_id: int, username: str | None, **kwargs
    ):
        try:
            return await self._client.request(
                method, path, headers=self._headers(telegram_id, username), **kwargs
            )
        except httpx2.HTTPError as exc:
            raise ApiError(type(exc).__name__) from exc

    async def register(self, telegram_id: int, username: str | None = None) -> dict:
        """Создаёт пользователя при первом обращении и обновляет его username."""
        response = await self._request("GET", "/me", telegram_id, username)
        if response.status_code != 200:
            raise ApiError(f"status {response.status_code}")
        return response.json()

    async def save_url(
        self, telegram_id: int, username: str | None, url: str
    ) -> SaveResult:
        response = await self._request(
            "POST", "/contents", telegram_id, username, json={"url": url}
        )
        if response.status_code == 201:
            return SaveResult("saved", content=response.json())
        if response.status_code == 409:
            return SaveResult("duplicate", existing_id=_existing_id(response))
        if response.status_code == 422:
            return SaveResult("invalid")
        raise ApiError(f"status {response.status_code}")

    async def get_content(
        self, telegram_id: int, username: str | None, content_id: int
    ) -> dict | None:
        """Нужен только для красивого ответа: при любой неудаче вернёт None."""
        try:
            response = await self._request(
                "GET", f"/contents/{content_id}", telegram_id, username
            )
        except ApiError:
            return None
        return response.json() if response.status_code == 200 else None

    async def close(self) -> None:
        await self._client.aclose()