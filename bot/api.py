import httpx2


class ApiError(Exception):
    """API недоступен или вернул ошибку. Текст не содержит секретов."""


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

    async def register(self, telegram_id: int, username: str | None = None) -> dict:
        """Создаёт пользователя при первом обращении и обновляет его username."""
        try:
            response = await self._client.get(
                "/me", headers=self._headers(telegram_id, username)
            )
        except httpx2.HTTPError as exc:
            raise ApiError(type(exc).__name__) from exc
        if response.status_code != 200:
            raise ApiError(f"status {response.status_code}")
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()