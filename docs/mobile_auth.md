# Блок 3: мобильная авторизация

17.11.2026 пользователь подтвердил установку каркаса на Samsung S25, разрешил коммиты и следующий блок. Созданы `36bacc1` (накопленная серверная подготовка) и `23b8a5f` (каркас). Изменения блока 3 подготовлены отдельно; блок 4 не разрешён.

## Реализованный контракт

Один аккаунт e-mail/пароль, общие правила паролей, consent, нормализации и rate limit. Бизнес-логика регистрации/проверки пароля вынесена в общие функции существующего auth-модуля; сайт продолжает использовать прежние `/auth/*` и HttpOnly cookie.

`auth_sessions.client_type`: `web` или `mobile`, default `web`. В БД только SHA-256 токена; mobile выдаёт случайный opaque Bearer, без JWT/refresh и Set-Cookie. Web-токен в Authorization и mobile-токен в cookie не принимаются. Смешанные credentials отклоняются; у cookie-запросов прежняя CSRF-проверка имеет приоритет (403 при нарушении Origin, иначе mixed → 401). Мобильный namespace отвергает session-cookie, Origin и Sec-Fetch-Site; анонимные запросы не принимают Authorization.

Общие `/me`, `/contents` и остальные защищённые ресурсы поддерживают оба транспорта на уровне backend. Клиент блока 3 использует `/mobile/auth/*`. С 18.11.2026 конфигурация публичного закрытого стенда также направляет мобильные запросы к маршрутам материалов и категорий через нативную ветку шлюза. [Правило и условия проверки](staging.md#мобильная-библиотека-блок-4)

Сроки прежние: 14 дней простоя, максимум 60 от создания, продление с шагом от суток, 10 сессий суммарно на аккаунт. Logout отзывает одну mobile-сессию; смена пароля сохраняет текущую web/mobile-сессию и отзывает остальные; reset отзывает все. Все mobile-ответы и запросы с Authorization имеют no-store, ошибки валидации не возвращают исходные password/token.

| Метод | Путь `/mobile/auth` | Данные / ответ |
|---|---|---|
| POST | `/register` | `{email,password,consent,timezone?}` → 201, mobile login result |
| POST | `/login` | `{email,password}` → 200, mobile login result |
| GET | `/session` | Bearer → `{user,expires_at,absolute_expires_at}`, без повторной выдачи токена |
| POST | `/logout` | Bearer → 204; неизвестный/отозванный токен → 401 |
| POST | `/password-reset/request` | `{email}` → 202 с нейтральным ответом |
| POST | `/password-reset/confirm` | `{token,password}` → 204, без автоматического входа |
| POST | `/email-verification/request` | Bearer → 202; уже подтверждён → 409 |
| POST | `/email-verification/confirm` | `{token}` → 204; не требует входа |

Login result: `{user,token,token_type:"Bearer",expires_at,absolute_expires_at}`. `user` — прежний UserOut, даты ISO 8601. Идентификаторы остаются JSON-числами совместимо с MVP; клиент принимает только safe integer и отклоняет значения с риском потери точности. Представление идентификаторов новых мобильных ресурсов уточняется перед блоком 4.

## Поведение клиента

- Формы входа, регистрации с явным consent, восстановления, подтверждения, профиль и выход. Библиотека, SQLite/очередь и push не реализуются в этом блоке.
- `expo/fetch`: только HTTPS origin без встроенных credentials/параметров, credentials=omit, redirect=error, timeout 20 секунд. Парольные POST не повторяются автоматически. Ошибки контролируемые, сырые ответы/исключения и токены в UI/логах не печатаются.
- SecureStore: отдельный service, WHEN_UNLOCKED_THIS_DEVICE_ONLY, token + version + origin. Профиль не сохраняется; сессионный токен не входит в React context/state или router params. Запись проверяется чтением, удаление проверяется отсутствием.
- Несекретный маркер установки в OS cache: при отсутствии сначала очищаются старые Keychain credentials. Это защищает от незаметного восстановления после переустановки iOS; удаление кэша ОС также консервативно завершает локальную сессию. Реальный reinstall/backup restore на iPhone пока не проверен.
- Старт/возврат на передний план проверяет серверную сессию. Сеть/5xx/401 Basic шлюза не стирают токен. Подтверждённый API 401 закрывает доступ к authenticated UI даже при ошибке очистки; требуется повторить очистку на разблокированном устройстве.
- При ошибке remote logout сессия остаётся до повторной попытки либо явного выбора «Выйти только на устройстве». Последний вариант не подтверждает отзыв на сервере; серверные сроки сохраняются.
- Post-confirm ошибки refresh/очистки не объявляют уже выполненную одноразовую операцию неуспешной. UI сообщает результат и отдельное ограничение, не предлагает молча повторить consumed token.

## Ссылки из писем

Существующие `/app/reset.html#token=...` и `/app/verify.html#token=...` остаются web fallback. Native принимает только exact HTTPS origin сборки, эти два пути и корректный единственный token во fragment. Одноразовый токен хранится лишь в памяти до 30 минут, не попадает в путь навигации. Старое завершение запроса не очищает более новую входящую ссылку. Для закрытого теста можно вручную вставить полную ссылку в «Аккаунт → Открыть ссылку из письма»; поле скрывает значение, автоматического чтения clipboard нет.

Android manifest содержит autoVerify/exact paths, iOS — associatedDomains. Backend публикует только явно заданные ассоциации:

- `MOBILE_APPLICATION_ID`: сейчас `ru.teleiosis.mobile.dev`.
- `MOBILE_ANDROID_CERT_SHA256`: JSON-массив SHA-256 отпечатков через `:`, default `[]` → endpoint 404.
- `MOBILE_APPLE_TEAM_ID`: пусто → AASA endpoint 404; нужна настоящая Apple team.

В приватном стенде настроен отпечаток текущего **debug** APK. В production потребуется настоящая подпись выпуска и согласованные app IDs. Public metadata endpoints не требуют gateway credentials, остальные приватные пути остаются защищены. Успешная генерация manifest/AASA не является проверкой OS association, холодного запуска или сохранения fragment на устройстве.

## Тестовый доступ и сборка

В `mobile/.env.example` только публичные параметры. APK 0.2.0/code2:

```sh
cd mobile
npm ci
EXPO_PUBLIC_API_ORIGIN=https://teleiosistest.tw1.ru EXPO_PUBLIC_STAGING_GATE=1 sh scripts/build-android-preview.sh
```

`mobile/artifacts/teleiosis-0.2.0-android-arm64-preview.apk`, 30 154 531 байт; SHA-256 `040f2e94adb97e6d7bdb26b1c72b0804bf868ebfb9da80b20996697cf2488d44`. Подпись v2 Android Debug совпадает с 0.1, проверены arm64/API24/target36, JS, archive alignment и конфигурация associations/backup. Это тестовая сборка, не магазинный выпуск.

Для `/mobile/*` gateway Basic передаётся отдельно в X-Staging-Authorization, Bearer восстанавливается proxy только после проверки gateway. Пароль шлюза вводится в «Доступ к тестовому стенду» и хранится в SecureStore с привязкой к origin; он не включён в APK/EXPO_PUBLIC. Только владелец через доверенную консоль читает `/srv/teleiosis/deploy/.env.staging-access`; не присылать пароль и письма в чат.

Публичный HTTPS proxy пока выключен. Поэтому вход с телефона ещё не проверен: API доступен только с сервера по loopback8443 с внутренним CA. Для S25 нужен согласованный запуск публичного proxy и настоящая выдача/проверка сертификата. Не обходить TLS и не подменять это HTTP или trust-all. Письма на стенде перехватываются, использовать только синтетические данные; юридический consent пока draft-1.

## Миграция и откат

Добавление k2a4b6c8d0e1 не удаляет аккаунты/материалы и сохраняет web-сессии. На приватном сервере создан и восстановлен backup до изменения; применена миграция, обновлены API/worker/private proxy. Новый image `teleiosis:mobile-auth-20261117`, прежний образ сохранён.

**Не возвращать старый код, оставив активные mobile-сессии:** он не проверяет client_type. При откате сначала остановить обслуживающий API/worker и выполнить новым образом `alembic downgrade j1f3a5b7c9d0` — это отзывает mobile-сессии и удаляет колонку, сохраняет web-сессии/остальные данные. Затем вернуть прежние image/env/preview proxy. Private env snapshot сохранён на сервере с 0600; его не копировать в отчёты/Git. Основную БД из backup автоматически не восстанавливать.

## Проверки и открытая приёмка

- Python/API: **764 passed in 66.89s**, отдельная PostgreSQL/контейнеры без host ports, удалены после проверки. Существующий web suite включён.
- Реальный Alembic upgrade/downgrade/upgrade, schema parity; отдельная проверка сохранения web и отзыва mobile при downgrade.
- **64 mobile tests / 9 suites**, tsc/lint: транспорт, отсутствие автоповторов, gateway401 vs API401, storage read-back/delete/error/reinstall marker, состояние при 401 и неудачной очистке, формы/consent, cold/warm routing, одноразовые ссылки и гонки. Нативные API в этих тестах mocked.
- JS/Hermes export обеих ОС; prebuild Android/iOS, native-config assertions; Android assembleRelease и подпись/manifest. iOS binary/device отсутствуют.
- Реальный Caddy HTTPS-test проверяет Basic/Bearer, anonymous mobile, browser compatibility, public metadata и private paths; включён в backend CI. Remote GitHub workflows ещё не запускались.
- Private HTTPS smoke **реального обновлённого API** прошёл регистрацию/вход/разделение credentials/verify/reset/отзыв/logout; свой аккаунт и MIME удалены. Сессионные токены/пароли не выводились.

Открыты: публичный сертификат/проверка входа и lifecycle на S25 для 0.2, verified App/Universal Links на устройствах, iOS resources и бинарник; остальные share/push пункты блока 2. Внешняя SMTP-доставка/правовой текст/retention и отдельная копия backup вне VM остаются условиями следующих приёмок. npm при установке сообщает 22 moderate advisories в дереве инструментов; force-исправления со сменой SDK не применялись, разбор до выпуска остаётся обязательным. Полная приёмка блока 3 не объявляется завершённой только по mocks/private smoke.
