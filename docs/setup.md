# Запуск проекта

Мобильный Android/iOS клиент (каркас и auth): отдельная инструкция [mobile/README.md](../mobile/README.md). Здесь описывается существующий backend/сайт.


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
| APP_ENV | `dev` (по умолчанию), `staging` или `prod`. В staging/prod обязательны COOKIE_SECURE=true, https:// и длинный SECRET_KEY |
| APP_ORIGIN | Адрес сайта в браузере (по умолчанию http://localhost:8000). Сайт нужно открывать именно по этому адресу: с http://127.0.0.1:8000 изменяющие запросы будут отклонены |
| COOKIE_SECURE | `false` в разработке (http://localhost), `true` на боевом сервере |
| EMAIL_BACKEND | `console` только dev; `smtp` для доставки; `capture` только staging, закрытые MIME-файлы без отправки. В prod допустим только smtp |
| CAPTURE_EMAIL_DIR | Абсолютный приватный каталог для staging/capture, по умолчанию /var/lib/teleiosis/captured-mail; владелец — uid процесса, права 0700 |
| SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_SECURITY | Почтовый сервер (`starttls`, `ssl`; `none` только в dev); нужны при `EMAIL_BACKEND=smtp`, хост и отправитель обязательны |
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

Обычные API-тесты строят БД из моделей; дополнительно tests/test_email_auth_migration.py проверяет реальные миграции в отдельной откатываемой схеме. Это не заменяет проверку развёртывания. Следующие команды меняют БД из DATABASE_URL: выполнять только на выделенной проверочной базе, а не на рабочей базе с данными:
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

## Метрики закрытого тестирования
`python -m app.metrics`: отчёт с агрегатами (регистрации, активация, возвраты, доля изученных, напоминания) без персональных данных. Активный день определяется таблицей `user_activity`.

## Частые проблемы
- API не стартует с ошибкой про DATABASE_URL: не заполнен .env или контейнер базы не запущен (`docker compose up -d`).

## Подготовка mobile (план, не инструкции запуска готового клиента)

На 16.11.2026 mobile/ и мобильных сборок ещё нет. Блок 0 подготовил документацию; пользователь подтвердил блок 1. Контейнеры/CI/backup подготовлены и проверяются локально, российский сервер ещё не выбран. Production-инструкция: [deployment.md](deployment.md), кандидаты: [infrastructure_options.md](infrastructure_options.md). Старый docker-compose.yml и команды разработки выше остаются действующими. План: [mobile_plan.md](mobile_plan.md), архитектура: [architecture.md](architecture.md).

GitHub workflow .github/workflows/backend.yml запускает Python suite, настоящий Alembic entrypoint на отдельной БД, сборку контейнеров, smoke/backup/restore/proxy/restart. Remote-запуск в GitHub в этой сессии не выполнялся. Для ручной проверки `python scripts/check_migrations.py` требует пустую БД с именем, заканчивающимся на `_migration_test`, через DATABASE_URL; рабочую БД не использовать. Скрипт не удаляет таблицы или БД и отказывается от занятой базы.

Для блока 1 подтвердить российский хостинг/бюджет, домен/DNS, SMTP, способ хранения секретов и бэкапов; проверить HTTPS, restore и исходящую сеть. Для внешних тестеров сначала закрыть вопросы обработки данных и согласий с юристом. Локальный закрытый тест по сообщению пользователя уже состоялся; серверного теста ещё не было.

Для блока 2 подтвердить Node/toolchain выбранной Expo/RN, Android SDK/JDK, macOS/Xcode либо согласованный macOS CI, устройства Android/iPhone, способ подписи и аккаунты. Точные версии инструментов/минимальные ОС фиксируются после проверки совместимости. В текущем Linux PATH node/npm/java/adb не найдены; docker CLI есть, daemon не проверялся. Это не инвентаризация других компьютеров основателя.

Основные сценарии проверяются на реальных устройствах, а не только Expo Go/эмуляторе. Отдельно проверить Android без Google-сервисов, если такая поддержка согласована, и условия выбранного push SDK. Не передавать реальные пользовательские данные в зарубежный CI/логи/артефакты. Signing-ключи и токены провайдеров не добавлять в репозиторий.

`other/mobile_context.md` сохранён локально по запросу пользователя, но other/ исключён .gitignore. Общая дорожная карта и решения хранятся также в отслеживаемой docs/; игнорирование other/ не менялось.

На сервере подготовлен отдельный [staging с перехватом писем](staging.md): TELEIOSIS_STAGING=1 подключает compose.staging.yml и принудительно задаёт staging/capture. Не выставлять APP_ENV=dev для публичного сервера и не ослаблять production SMTP/TLS-проверки ради отсутствующей почты. Gateway-пароль, DB-секреты и SECRET_KEY генерируются только на сервере; их не выводят в конфигурационных отчётах.

Мобильная авторизация и миграция k2a4b6c8d0e1, staging-доступ и rollback: [mobile_auth.md](mobile_auth.md). Не откатывать backend к версии без client_type, оставляя активные mobile-сессии.
