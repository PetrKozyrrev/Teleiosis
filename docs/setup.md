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
| APP_ENV | `dev` (по умолчанию) или `prod`. В `prod` сервер не запустится без COOKIE_SECURE=true и адреса https:// |
| APP_ORIGIN | Адрес сайта в браузере (по умолчанию http://localhost:8000). Сайт нужно открывать именно по этому адресу: с http://127.0.0.1:8000 изменяющие запросы будут отклонены |
| COOKIE_SECURE | `false` в разработке (http://localhost), `true` на боевом сервере |
| EMAIL_BACKEND | `console` (по умолчанию, письма печатаются в терминал с uvicorn) или `smtp`. В `prod` допустим только `smtp` |
| SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_SECURITY | Почтовый сервер (`starttls`, `ssl` или `none`); нужны при `EMAIL_BACKEND=smtp`, хост и отправитель обязательны |
| SECRET_KEY | Секрет подписи ссылок отписки, не короче 32 символов. В `prod` обязателен; в dev без него отписка и воркер напоминаний не работают. Смена ключа делает недействительными все выданные ссылки. Создать: `printf '\nSECRET_KEY=%s\n' "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" >> .env` |

Для разработки нужны переменные PostgreSQL, DATABASE_URL и TEST_DATABASE_URL. Для писем и воркера настройте SECRET_KEY и EMAIL_BACKEND.


## Ежедневный запуск (в каждом терминале `source .venv/bin/activate`)

```bash
docker compose up -d
uvicorn app.main:app --reload
```
Процесс напоминаний запускается во втором терминале (`source .venv/bin/activate`, затем `python -m app.worker`). Ему нужен `SECRET_KEY` в `.env`. Он проверяет подборки раз в минуту, допускает только один экземпляр и не перезапускается сам при изменении кода (остановите Ctrl+C и запустите заново). В режиме `EMAIL_BACKEND=console` письма печатаются в терминале воркера, а не uvicorn.

## Сайт
После запуска `uvicorn app.main:app --reload` откройте http://localhost:8000/ (откроется /app/). Сайт нужно открывать именно по адресу из APP_ORIGIN (по умолчанию localhost, не 127.0.0.1), иначе изменяющие запросы будут отклонены. Письма сброса пароля и подтверждения e-mail в разработке печатаются в терминал с uvicorn, письма подборки и напоминаний в терминал воркера.

## Тесты
```bash
python -m pytest -v
```

## Миграции
Миграция `j1f3a5b7c9d0` удаляет `users.telegram_id` и `users.username`, делает e-mail обязательным. Перед обновлением остановите API и воркер и сохраните резервную копию БД. Если есть аккаунты без e-mail, миграция остановится до изменения схемы: назначьте им реальные адреса, затем повторите обновление. Для аккаунтов без пароля после назначения e-mail можно использовать обычный сброс пароля. Аккаунты и материалы автоматически не удаляются.

Откат на одну ревизию восстанавливает столбцы, но не удалённые Telegram-идентификаторы: их можно восстановить только из резервной копии. Старые миграции сохранены для обновления существующих баз и установки с нуля.

Проверка новой миграции вручную (тесты строят БД из моделей и расхождений с миграциями не видят):
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

## Метрики закрытого тестирования
`python -m app.metrics`: отчёт с агрегатами (регистрации, активация, возвраты, доля изученных, напоминания) без персональных данных. Активный день определяется таблицей `user_activity`.

## Частые проблемы
- API не стартует с ошибкой про DATABASE_URL: не заполнен .env или контейнер базы не запущен (`docker compose up -d`).