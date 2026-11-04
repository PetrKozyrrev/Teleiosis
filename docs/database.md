Итоговая схема (4 таблицы)
users
| Поле | Тип | Ограничения |
| :--- | :--- | :--- |
| **id** | BIGINT, identity | PK |
| **telegram_id** | BIGINT | NOT NULL, UNIQUE |
| **username** | TEXT | NULL |
| **timezone** | TEXT | NOT NULL, по умолчанию 'UTC' |
| **reminders_enabled** | BOOLEAN | NOT NULL, по умолчанию true |
| **reminder_time** | TIME | NOT NULL, по умолчанию '09:00' |
| **created_at** | TIMESTAMPTZ | NOT NULL, по умолчанию now() |


Telegram ID превышает размер обычного INTEGER, поэтому тип BIGINT.

categories
| Поле       | Тип               | Ограничения                                              |
|------------|-------------------|----------------------------------------------------------|
| id         | BIGINT, identity  | PK                                                       |
| user_id    | BIGINT            | NOT NULL, FK → users(id), ON DELETE CASCADE              |
| name       | TEXT              | NOT NULL, длина 1–50                                     |
| created_at | TIMESTAMPTZ       | NOT NULL, now()                                          |

Уникальность: (user_id, name), чтобы у пользователя не было двух категорий с одним названием.

contents
| Поле           | Тип               | Ограничения                                              |
|----------------|-------------------|----------------------------------------------------------|
| id             | BIGINT, identity  | PK                                                       |
| user_id        | BIGINT            | NOT NULL, FK → users(id), ON DELETE CASCADE              |
| category_id    | BIGINT            | NULL, FK → categories(id), ON DELETE SET NULL            |
| title          | TEXT              | NOT NULL                                                 |
| url            | TEXT              | NULL                                                     |
| url_normalized | TEXT              | NULL                                                     |
| description    | TEXT              | NULL                                                     |
| note           | TEXT              | NULL                                                     |
| content_type   | TEXT              | NOT NULL, по умолчанию 'other'                           |
| source         | TEXT              | NOT NULL, по умолчанию 'other'                           |
| image_url      | TEXT              | NULL                                                     |
| status         | TEXT              | NOT NULL, по умолчанию 'unseen', CHECK                   |
| studied_at     | TIMESTAMPTZ       | NULL                                                     |
| created_at     | TIMESTAMPTZ       | NOT NULL, now()                                          |
| updated_at     | TIMESTAMPTZ       | NOT NULL, now()                                          |

Ограничения:

CHECK (status IN ('unseen','planned','studied','irrelevant'));
UNIQUE (user_id, url_normalized);
CHECK (url IS NOT NULL OR note IS NOT NULL): материал без ссылки обязан иметь текст.

Значения content_type (video, article, post, note, other) и source (youtube, telegram, web, other) хранятся как текст без жёсткого CHECK: новые источники будут добавляться, а менять ограничение в базе при каждом новом источнике неудобно. Допустимые значения будет проверять код.

Правило удаления категории: материалы не удаляются, у них category_id становится NULL («Без категории»).

reminders
| Поле         | Тип               | Ограничения                                              |
|--------------|-------------------|----------------------------------------------------------|
| id           | BIGINT, identity  | PK                                                       |
| user_id      | BIGINT            | NOT NULL, FK → users(id), ON DELETE CASCADE              |
| content_id   | BIGINT            | NOT NULL, FK → contents(id), ON DELETE CASCADE           |
| scheduled_at | TIMESTAMPTZ       | NOT NULL                                                 |
| status       | TEXT              | NOT NULL, по умолчанию 'pending', CHECK                  |
| created_at   | TIMESTAMPTZ       | NOT NULL, now()                                          |

CHECK (status IN ('pending','sent','cancelled'))

Время всегда хранится в UTC (TIMESTAMPTZ), а перевод в часовой пояс пользователя делается при показе и при расчёте времени отправки. Это решает требование техплана про разные часовые пояса.

Индексы
| Таблица   | Индекс                                      | Зачем                                                          |
|-----------|---------------------------------------------|----------------------------------------------------------------|
| contents  | (user_id, created_at DESC)                  | Список библиотеки, последние сохранения                        |
| contents  | (user_id, status)                           | Фильтр по статусу, статистика                                  |
| contents  | (user_id, category_id)                      | Фильтр по категории                                            |
| reminders | (scheduled_at) WHERE status = 'pending'     | Планировщик быстро находит то, что пора отправить              |
| reminders | (content_id)                                | Каскадное удаление и просмотр напоминаний материала            |

Индекс по telegram_id и (user_id, name) создаются автоматически благодаря UNIQUE.

Поиск по названию в MVP реализуем через ILIKE. На объёмах в сотни материалов на пользователя этого достаточно, отдельные индексы под поиск не нужны.

Правила удаления (сводка)
| Что удаляем | Что происходит |
|---|---|
| Пользователь | Удаляются его категории, материалы и напоминания |
| Материал | Удаляются его напоминания |
| Категория | Материалы остаются, `category_id` = NULL |