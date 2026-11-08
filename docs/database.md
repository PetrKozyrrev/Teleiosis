# База данных (PostgreSQL 16)

Итоговая схема: 6 таблиц (users, categories, contents, reminders, auth_sessions, rate_limit_events). Схема меняется только миграциями Alembic. Время всегда хранится в UTC (TIMESTAMPTZ), перевод в часовой пояс пользователя делается при показе и при расчёте времени отправки.

## users
| Поле | Тип | Ограничения |
|---|---|---|
| id | BIGINT, identity | PK |
| telegram_id | BIGINT | NULL, UNIQUE (нужен только пользователям из Telegram, заморожено) |
| username | TEXT | NULL |
| email | TEXT | NULL, UNIQUE, CHECK email = lower(email), длина не больше 254 |
| password_hash | TEXT | NULL, CHECK: хэш возможен только при заданном e-mail |
| email_verified_at | TIMESTAMPTZ | NULL |
| consent_at | TIMESTAMPTZ | NULL |
| consent_version | TEXT | NULL, CHECK: consent_at и consent_version задаются парой |
| timezone | TEXT | NOT NULL, по умолчанию 'UTC' |
| reminders_enabled | BOOLEAN | NOT NULL, по умолчанию true |
| reminder_time | TIME | NOT NULL, по умолчанию '09:00' |
| created_at | TIMESTAMPTZ | NOT NULL, по умолчанию now() |

Дополнительно CHECK (email IS NOT NULL OR telegram_id IS NOT NULL): у пользователя есть хотя бы один способ входа. Уникальность не мешает нескольким значениям NULL, поэтому пользователи без Telegram или без e-mail не конфликтуют. Приложение само приводит e-mail к нижнему регистру, а БД это проверяет. В хэше пароля лежит строка Argon2id целиком (соль внутри). Telegram ID превышает размер INTEGER, поэтому BIGINT. Настройки напоминаний хранятся в users (связь 1:1).

## categories
| Поле | Тип | Ограничения |
|---|---|---|
| id | BIGINT, identity | PK |
| user_id | BIGINT | NOT NULL, FK users(id), ON DELETE CASCADE |
| name | TEXT | NOT NULL, длина 1-50 |
| created_at | TIMESTAMPTZ | NOT NULL, now() |

Уникальность (user_id, name): у пользователя не бывает двух категорий с одним названием. Названия различаются по регистру (известное ограничение).

## contents
| Поле | Тип | Ограничения |
|---|---|---|
| id | BIGINT, identity | PK |
| user_id | BIGINT | NOT NULL, FK users(id), ON DELETE CASCADE |
| category_id | BIGINT | NULL, FK categories(id), ON DELETE SET NULL |
| title | TEXT | NOT NULL |
| url | TEXT | NULL |
| url_normalized | TEXT | NULL |
| description | TEXT | NULL |
| note | TEXT | NULL |
| content_type | TEXT | NOT NULL, по умолчанию 'other' |
| source | TEXT | NOT NULL, по умолчанию 'other' |
| image_url | TEXT | NULL |
| status | TEXT | NOT NULL, по умолчанию 'unseen', CHECK |
| studied_at | TIMESTAMPTZ | NULL |
| created_at | TIMESTAMPTZ | NOT NULL, now() |
| updated_at | TIMESTAMPTZ | NOT NULL, now() |

Ограничения:
- CHECK (status IN ('unseen','planned','studied','irrelevant')).
- UNIQUE (user_id, url_normalized): защита от дублей (для заметок url_normalized равен NULL, они не конфликтуют).
- CHECK (url IS NOT NULL OR note IS NOT NULL): материал без ссылки обязан иметь текст.

Значения content_type (video, article, post, note, other) и source (youtube, telegram, web, other) хранятся как текст без CHECK: новые источники будут добавляться, а менять ограничение при каждом новом источнике неудобно. Допустимые значения проверяет код.

Одна категория на материал (category_id). Теги в MVP-схему не входят.

## reminders
| Поле | Тип | Ограничения |
|---|---|---|
| id | BIGINT, identity | PK |
| user_id | BIGINT | NOT NULL, FK users(id), ON DELETE CASCADE |
| content_id | BIGINT | NOT NULL, FK contents(id), ON DELETE CASCADE |
| scheduled_at | TIMESTAMPTZ | NOT NULL |
| status | TEXT | NOT NULL, по умолчанию 'pending', CHECK |
| created_at | TIMESTAMPTZ | NOT NULL, now() |

CHECK (status IN ('pending','sent','cancelled')). Защиты от дублей нет; модель напоминаний будет выбрана на этапе 7.

## auth_sessions
| Поле | Тип | Ограничения |
|---|---|---|
| id | BIGINT, identity | PK |
| user_id | BIGINT | NOT NULL, FK users(id), ON DELETE CASCADE |
| token_hash | TEXT | NOT NULL, UNIQUE, CHECK длина 64 (hex SHA-256) |
| created_at | TIMESTAMPTZ | NOT NULL, now() |
| expires_at | TIMESTAMPTZ | NOT NULL, CHECK expires_at > created_at |

Сам токен не хранится, только хэш.

## rate_limit_events
| Поле | Тип | Ограничения |
|---|---|---|
| id | BIGINT, identity | PK |
| bucket | TEXT | NOT NULL (название счётчика: login_ip, login_email_ip, register_ip) |
| key_hash | TEXT | NOT NULL, CHECK длина 64 (SHA-256 от адреса или e-mail) |
| created_at | TIMESTAMPTZ | NOT NULL, now() |

Журнал попыток для ограничения частоты запросов (скользящее окно). Адрес и e-mail в открытом виде не хранятся. Записи старше 2 часов удаляются при каждой новой записи. Связей с другими таблицами нет.

## Индексы
| Таблица | Индекс | Зачем |
|---|---|---|
| contents | (user_id, created_at DESC) | Список библиотеки, последние сохранения |
| contents | (user_id, status) | Фильтр по статусу, статистика |
| contents | (user_id, category_id) | Фильтр по категории |
| reminders | (scheduled_at) WHERE status = 'pending' | Планировщик быстро находит то, что пора отправить |
| reminders | (content_id) | Каскадное удаление и просмотр напоминаний материала |
| auth_sessions | (user_id) | Каскадное удаление и очистка сессий пользователя |
| rate_limit_events | (bucket, key_hash, created_at) | Подсчёт попыток за окно |
| rate_limit_events | (created_at) | Быстрое удаление устаревших записей |

Индексы по telegram_id, (user_id, name), (user_id, url_normalized) и token_hash создаются автоматически благодаря UNIQUE.

Поиск по названию в MVP работает через ILIKE с экранированием % и _. На сотнях материалов на пользователя этого достаточно, отдельные индексы под поиск не нужны.

## Правила удаления
| Что удаляем | Что происходит |
|---|---|
| Пользователь | Удаляются его категории, материалы, напоминания и сессии |
| Материал | Удаляются его напоминания |
| Категория | Материалы остаются, category_id становится NULL («Без категории») |

## Предстоящие изменения (не применены, предварительно)
Окончательно утверждаются на шаге этапа 6 перед написанием миграций.
- users: telegram_id становится необязательным; добавляются e-mail (уникальный, нормализованный), хэш пароля, время подтверждения e-mail, дата и версия согласия на обработку данных; ограничение «задан e-mail или telegram_id».
- Таблица одноразовых токенов сброса пароля.
- auth_sessions: возможно время последнего использования (продление сессии).
- contents: фиксация открытия материала (дата последнего открытия, счётчик).
- reminders: выбор модели и защита от дублей (этап 7).

Каждая миграция проверяется вручную: `alembic upgrade head` и `alembic downgrade -1` (тесты строят БД из моделей и расхождение с миграциями не ловят).