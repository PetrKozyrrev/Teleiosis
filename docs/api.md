# API (FastAPI)

Интерактивная документация при запущенном сервере: http://127.0.0.1:8000/docs

## Авторизация
Пользователь определяется зависимостью `get_current_user` (app/deps.py). Способы:
1. Бот: заголовки `X-Bot-Key` (секрет, не короче 32 символов) + `X-Telegram-Id`
   + необязательно `X-Telegram-Username`. Пользователь создаётся при первом запросе.
2. ВРЕМЕННО, только разработка: `X-Dev-Telegram-Id` при `DEV_AUTH_ENABLED=true`.
   Будет удалён на этапе 5.
3. Mini App: POST /auth/telegram выдаёт токен сессии (24 часа, без продления);
   далее заголовок `Authorization: Bearer <токен>`. Если передан Authorization,
   другие способы входа не используются (вместе с X-Bot-Key или X-Dev-Telegram-Id: 401).

Ошибки: нет или неверные данные входа дают 401; чужой или несуществующий ресурс
даёт 404 (не 403); идентификаторы вне диапазона BIGINT дают 422.

## Эндпоинты
| Метод и путь | Назначение | Ответы |
|---|---|---|
| GET /health | Проверка работы, без авторизации | 200 |
| GET /me | Текущий пользователь (создаётся при первом обращении) | 200, 401 |
| POST /categories | Создать категорию `{name}` (1–50 символов после обрезки пробелов) | 201, 409 дубль, 422 |
| GET /categories | Список своих категорий по алфавиту | 200 |
| PATCH /categories/{id} | Переименовать `{name}` | 200, 404, 409, 422 |
| DELETE /categories/{id} | Удалить; материалы остаются без категории | 204, 404 |
| POST /contents | Сохранить `{url?, note?, title?, category_id?}`, нужен url или note | 201, 404 чужая категория, 409 дубль, 422 |
| GET /contents | Список (см. параметры ниже) | 200, 422 |
| GET /contents/{id} | Один материал | 200, 404 |
| PATCH /contents/{id} | Изменить только `title`, `note`, `status`, `category_id`; лишние поля дают 422 | 200, 404, 422 |
| DELETE /contents/{id} | Удалить (напоминания удаляются каскадом) | 204, 404 |
| POST /auth/telegram | Обмен initData на токен сессии `{init_data}` → `{token, token_type, expires_at, user}` | 200, 401 любая ошибка проверки, 422, 503 нет BOT_TOKEN |

### POST /contents
- Ссылка нормализуется (https, без www, без трекинговых параметров и #фрагмента;
  YouTube приводится к youtube.com/watch?v=ID; t.me без параметров).
- Дубль среди материалов пользователя: 409 с телом
  `{"detail": {"message": "Already saved", "existing_id": N}}`.
- Название: из запроса, иначе загруженное со страницы, иначе временное
  (адрес без https:// или первая строка заметки). Загрузка метаданных best-effort,
  защита от SSRF (app/metadata.py), YouTube через oEmbed.

### GET /contents: параметры
`q` (поиск по названию), `status` (unseen, planned, studied, irrelevant),
`source` (youtube, telegram, web, other), `category_id`, `uncategorized` (true),
`sort` (newest, oldest, title), `limit` (1–100, по умолчанию 20), `offset`.
`category_id` вместе с `uncategorized` даёт 422.
Ответ: `{items, total, limit, offset}`.

### Статусы
Один статус на материал, переходы свободные. `studied_at` ставится при входе
в «studied» и очищается при выходе.
