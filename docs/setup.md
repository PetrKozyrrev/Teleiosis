# Запуск проекта


## Первый запуск
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       
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
| BOT_TOKEN | Токен из @BotFather. Нужен только боту и входу по Telegram (заморожены) |
| BOT_API_KEY | Секрет бота для входа в API, не короче 32 символов. Нужен только боту. Пустой = вход ботом отключён |
| API_BASE_URL | Адрес API для бота (http://127.0.0.1:8000) |
| TELEGRAM_PROXY | Прокси только для запросов бота к Telegram; пусто, если Telegram доступен напрямую |

Для работы API и будущего сайта достаточно переменных PostgreSQL, DATABASE_URL и TEST_DATABASE_URL.

Ключ бота (если бот понадобится): `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Ежедневный запуск (два терминала, в каждом `source .venv/bin/activate`)
```bash
docker compose up -d
uvicorn app.main:app --reload
```
После изменения .env перезапускайте uvicorn.

## Telegram-бот (заморожен)
Запускается только при необходимости, в третьем терминале, в одном экземпляре:
```bash
python -m bot.main
```
Нужны BOT_TOKEN, BOT_API_KEY и, если Telegram недоступен напрямую, TELEGRAM_PROXY. После изменения .env бот перезапускается вручную.

## Тесты
```bash
python -m pytest -v
```

## Миграции
Проверка новой миграции вручную (тесты строят БД из моделей и расхождений с миграциями не видят):
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

## Частые проблемы
- Бот: `TelegramNetworkError` или тайм-аут: Telegram недоступен напрямую (VPN, прокси). aiohttp не читает переменные http_proxy, адрес задаётся в TELEGRAM_PROXY.
- Бот: `terminated by other getUpdates request`: запущено два экземпляра. `pkill -f "bot.main"`, подождать 30 секунд, запустить один.
- Бот отвечает «Сервис временно недоступен» при запущенном API: проверить BOT_API_KEY и перезапустить uvicorn.
- API не стартует с ошибкой про DATABASE_URL: не заполнен .env или контейнер базы не запущен (`docker compose up -d`).