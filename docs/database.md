# База данных (PostgreSQL 16)

Итоговая схема: 9 таблиц (users, categories, contents, reminders, auth_sessions, rate_limit_events, password_reset_tokens, user_activity, email_verification_tokens). Схема меняется только миграциями Alembic. Время всегда хранится в UTC (TIMESTAMPTZ), перевод в часовой пояс пользователя делается при показе и при расчёте времени отправки.

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

Уникальность без учёта регистра: уникальный индекс (user_id, lower(name)), «Бизнес» и «бизнес» это одна категория. Ограничение (user_id, name) удалено как лишнее. Функция lower() зависит от локали БД: в UTF-8 локали (как в нашем контейнере) кириллица обрабатывается верно; при создании боевой БД проверить локаль.

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
| last_opened_at | TIMESTAMPTZ | NULL (когда последний раз открывали исходную ссылку) |
| open_count | INTEGER | NOT NULL, по умолчанию 0, CHECK open_count >= 0 |
| created_at | TIMESTAMPTZ | NOT NULL, now() |
| updated_at | TIMESTAMPTZ | NOT NULL, now() |


Ограничения:
- CHECK (status IN ('unseen','planned','studied','irrelevant')).
- UNIQUE (user_id, url_normalized): защита от дублей (для заметок url_normalized равен NULL, они не конфликтуют).
- CHECK (url IS NOT NULL OR note IS NOT NULL): материал без ссылки обязан иметь текст.
- CHECK (open_count >= 0).

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

CHECK (status IN ('pending','sent','cancelled')). У материала не больше одного ожидающего напоминания (частичный уникальный индекс). Отмена ставит cancelled, отправка sent; строки не удаляются (история). Подборка отдельной таблицы не имеет: считается из users.

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
| bucket | TEXT | NOT NULL (название счётчика: login_ip, login_email_ip, register_ip, reset_email, reset_ip) |
| key_hash | TEXT | NOT NULL, CHECK длина 64 (SHA-256 от адреса или e-mail) |
| created_at | TIMESTAMPTZ | NOT NULL, now() |

Журнал попыток для ограничения частоты запросов (скользящее окно). Адрес и e-mail в открытом виде не хранятся. Записи старше 2 часов удаляются при каждой новой записи. Связей с другими таблицами нет.

## password_reset_tokens
| Поле | Тип | Ограничения |
|---|---|---|
| id | BIGINT, identity | PK |
| user_id | BIGINT | NOT NULL, FK users(id), ON DELETE CASCADE |
| token_hash | TEXT | NOT NULL, UNIQUE, CHECK длина 64 (hex SHA-256) |
| created_at | TIMESTAMPTZ | NOT NULL, now() |
| expires_at | TIMESTAMPTZ | NOT NULL, CHECK expires_at > created_at |

Токен сброса пароля живёт 1 час. Сам токен не хранится, только хэш. После использования строка удаляется (поля «использован» нет). Новый запрос удаляет прежние токены пользователя и все просроченные.

## user_activity
| Поле | Тип | Ограничения |
|---|---|---|
| user_id | BIGINT | PK (часть), FK users(id), ON DELETE CASCADE |
| day | DATE | PK (часть): местная дата пользователя (по `users.timezone`) в момент действия |

Активный день: день, в который пользователь сделал хотя бы одно действие с материалами (сохранил, изменил, открыл оригинал, поставил или перенёс напоминание). Просмотры страниц, вход, `GET`, настройки, категории и удаление не считаются. Нужна для метрик возврата (`python -m app.metrics`). Это поведенческие данные о пользователе: учесть в политике обработки ПДн, включать в выгрузку данных, удаляется вместе с аккаунтом.

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
| password_reset_tokens | (user_id) | Каскадное удаление и замена прежних токенов |
| categories | UNIQUE (user_id, lower(name)) | Уникальность названий без учёта регистра |
| reminders | UNIQUE (content_id) WHERE status = 'pending' | Один ожидающий на материал

Поиск по названию в MVP работает через ILIKE с экранированием % и _. На сотнях материалов на пользователя этого достаточно, отдельные индексы под поиск не нужны.

## Правила удаления
| Что удаляем | Что происходит |
|---|---|
| Пользователь | Удаляются его категории, материалы, напоминания, сессии, токены сброса пароля |
| Материал | Удаляются его напоминания |
| Категория | Материалы остаются, category_id становится NULL («Без категории») |

## Запланировано на этапе 7 (не применено; решения от 10.11.2026 в decisions.md)
Названия предварительные, окончательно утверждаются перед написанием каждой миграции.
- users: `last_digest_on` (DATE, NULL): локальная дата последней отправленной подборки, защита от двойной отправки. Позже `last_seen_at` (TIMESTAMPTZ, NULL) для метрик возврата.
- email_verification_tokens: по образцу password_reset_tokens (хэш токена, срок, каскадное удаление).
- reminders: частичный уникальный индекс (content_id) WHERE status = 'pending', у материала не больше одного ожидающего напоминания.

Каждая миграция проверяется вручную: `alembic upgrade head` и `alembic downgrade -1` (тесты строят БД из моделей и расхождение с миграциями не ловят).