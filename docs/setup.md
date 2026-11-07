# Запуск проекта

Среда: Windows + WSL2 (Ubuntu), Docker Desktop с интеграцией WSL, Python 3.12.
Проект лежит в ~/teleiosis внутри WSL. Все команды выполняются в WSL.

## Первый запуск
```bash
cd ~/teleiosis
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # затем заполнить значения (секреты в Git не попадают)
docker compose up -d
# если тестовой базы ещё нет:
docker exec teleiosis_db psql -U teleiosis -d teleiosis -c "CREATE DATABASE teleiosis_test;"
alembic upgrade head
```

## Переменные .env
| Переменная | Назначение |
|---|---|
| POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB | Контейнер PostgreSQL |
| DATABASE_URL | Рабочая база (читает API) |
| TEST_DATABASE_URL | Тестовая база teleiosis_test (должна отличаться от рабочей) |
| BOT_TOKEN | Токен из @BotFather |
| BOT_API_KEY | Секрет бота для входа в API, не короче 32 символов |
| API_BASE_URL | Адрес API для бота (http://127.0.0.1:8000) |
| TELEGRAM_PROXY | Прокси только для запросов к Telegram; пусто, если Telegram доступен напрямую |

Ключ бота: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Ежедневный запуск (три терминала, в каждом `source .venv/bin/activate`)
```bash
docker compose up -d
uvicorn app.main:app --reload
python -m bot.main
```
После изменения .env перезапускайте uvicorn и бота вручную.

## Тесты
```bash
python -m pytest -v
```

## Частые проблемы
- Бот: `TelegramNetworkError` / тайм-аут: Telegram недоступен напрямую (VPN, прокси).
  aiohttp не читает переменные http_proxy, адрес задаётся в TELEGRAM_PROXY.
- Бот: `terminated by other getUpdates request`: запущено два экземпляра.
  `pkill -f "bot.main"`, подождать 30 секунд, запустить один.
- Бот отвечает «Сервис временно недоступен» при запущенном API: проверить BOT_API_KEY
  и перезапустить uvicorn.