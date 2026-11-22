# Progress

## Недельный план включён на стенде, 22.11.2026

После проверки восстановления копии БД/PDF обновлён API и применена s9b1d3e5f7a8. Публичные HTTPS-проверки плана и PDF прошли, API healthy. APK 0.9.0 готов к ручной проверке на S25. [Протокол](mobile_week_plan.md).

## PostgreSQL и HTTP блока 10 проверены, 22.11.2026

Прошли 883 backend-теста и 26 подслучаев, Alembic upgrade/downgrade/upgrade и сверка моделей. HTTP-проверка собранного образа подтвердила сценарий недельного плана и изоляцию аккаунтов. Обновление стенда ожидает отдельного согласования. [Протокол](mobile_week_plan.md).

## Приёмка PDF на S25 и переход к блоку 10

22.11.2026 пользователь подтвердил работу создания отдельной PDF-карточки в APK 0.8.1 на Samsung S25 после обновления стенда. Проверка iOS остаётся открытой. Пользователь разрешил продолжить локальную разработку целей и ручного плана. [Контракт и проверки блока 10](mobile_week_plan.md).

## Подблок 9В — PDF включён на стенде, 21.11.2026

Обновление по согласованию пользователя. Образ `teleiosis:pdf-disk-20261121`, ревизия `r8a0c2e4f6b7`, сохранение PDF на приватном диске, сканирование ClamAV и плановое обслуживание. Прошли 868 backend-тестов, 26 подслучаев и сквозной HTTPS-прогон. APK 0.8.1 готов к ручной приёмке на S25. [Подробный протокол](mobile_pdf.md#согласованное-обновление-стенда--21112026)

## Подблок 9В — приватные PDF, 21.11.2026

Добавлены загрузка и просмотр одного PDF к сохранённому материалу, квоты, проверка, приватные объекты и повторяемая очистка. [Файлы, тесты и план согласования инфраструктуры](mobile_pdf.md).

## Подблок 9Б — локальный кандидат, 21.11.2026

Импорт JSON v1 с предпросмотром, атомарной записью и квитанцией повтора. Расширенный поиск по сохранённым полям с прежними фильтрами и пагинацией. Подготовлены APK 0.7.0/code13, локальный образ API и миграция p6e8f0a2b4c5. [Контракт, проверки и план отдельного rollout](mobile_import_search.md).

## Приёмка APK 0.6.0 — 21.11.2026

Пользователь сообщил «Проверка пройдена, все работает» после передачи APK 0.6.0 и согласованного обновления API. Приёмка подблока 9А на Samsung S25 (Android 17 / One UI 9.0) подтверждена пользователем. Это не закрывает iOS, реальные RuStore/APNs, отдельные App Links, SMTP, магазины и общий пилот. Следующий подблок — 9Б (импорт и расширенный поиск); в этом чате он не начинался. Пользователь запросил промпт для продолжения в новом чате. При проверке состояния HEAD `f5287f4` (mobile v0.6.0 android), рабочее дерево было чистым. Новые изменения — только запись этой приёмки, без commit/push.

## Подблок 9А — согласованный rollout, 20.11.2026

По отдельному «Да» пользователя сохранены backup/настройки и успешно проверено восстановление в отдельную БД, затем применены m4c6d8e0f2a3/n5d7e9f1a3b4 и обновлён только API. Образ teleiosis:organization-20261120, новая БД n5d7e9f1a3b4, API healthy, push false. Добавлен API/migrate image pin в staging overlay с прежним fallback, проверены реальный config diff и 7 deployment-script тестов. DB/worker/Caddy ID прежние, Caddyfile неизменен. Публичный HTTPS-прогон старых/новых API, двух аккаунтов, Secure-cookie/CSRF, экспорта и удаления прошёл; fixture-аккаунты и их строки удалены. Внешние TLS/gateway/private paths/assetlinks прошли. Архив /var/backups/teleiosis-9a-zg5fewjv/before-9a.dump сохранён. APK 0.6.0 прежний, требуется приёмка на S25 поверх 0.5.3. Commit/push не выполнялись, 9Б/9В не начаты. [Подробный результат](mobile_organization.md).

## Блок 9А — теги и коллекции, 20.11.2026

Пользователь подтвердил APK 0.5.3 и сообщил о push проекта. HEAD `0ee4e99`, рабочее дерево в начале чистое. Разрешено продолжение: 9А (организация), 9Б (импорт/поиск) и 9В (файлы) разделены, реализован только 9А. Добавлены приватные теги/коллекции, множественные назначения с If-Match, AND-фильтры, экспорт и owner-FK. Новая мобильная библиотека использует существующий staging namespace `/mobile/library/*`, Caddy не менялся. Очередь и submissions fingerprint прежние.

Прошли 833 backend-теста/26 подслучаев, 110 mobile/18 suites, TypeScript/lint, 5 toolchain, онлайн Expo check и npm audit0, JS export Android/iOS, native config Android/iOS default/experimental share, Alembic upgrade/downgrade/upgrade и schema parity. Отдельный HTTPS E2E с текущим API, двумя аккаунтами, браузерными cookie и CSRF прошёл в одноразовых контейнерах. Добавлен в CI, GitHub Actions ещё не запускался. APK 0.6.0/code12 собран и прошёл verifier с прежней подписью, 25 ELF/ZIP на 16 КиБ. SHA-256 `903759cfb456da229a632bed662b213a8c6993dbdf0b374b0f97195e1b4718ab`.

На стенде только чтением подтверждена ревизия l3b5c7d9e1f2. Для приёмки функций на S25 нужны согласованное обновление API и две миграции m4c6d8e0f2a3/n5d7e9f1a3b4, push останется выключен. Rollout, commit/push и публикация не выполнялись. Открытые iOS/push/пилот сохранены. [Артефакт, файлы, результаты и конкретный план обновления](mobile_organization.md).

## Блок 8 — исправление изоляции сессий, 20.11.2026

Кандидат 0.5.3/code11 связывает отложенный logout и библиотечный Request с исходной сессией. Старое подтверждение не отзывает новую сессию, старый экран не получает данные нового аккаунта. При logout ответы закрываются до локальной очистки, сбой очистки можно повторить для прежнего владельца. Две ошибки доказаны тестами до исправления, после прошли 100 мобильных тестов/17 suites, TS/lint, 5 проверок инструментов, 8 проверок verifier, онлайн Expo check/audit0 и JS export обеих ОС. APK собран и проверен: подпись прежняя, 25 ELF на 16 КиБ, SHA-256 `2343007d62f634370cd6eb595cb6e67aed914494008cb598d95b7e77837d8437`. Приёмка обновления поверх 0.5.2 на S25 открыта. [Артефакт и результаты](mobile_release.md#изоляция-сессий--кандидат-053-20112026).

Во время сборки среда перезапустилась и очистила/tmp. Инструменты восстановлены в игнорируемой папке other/mobile-tools, повторные100 тестов прошли. Предыдущие изменения audit/CI сохранены, API/Caddy не менялись. Коммит/push не выполнялись.

## Блок 8 — приёмка S25 и исправление зависимостей, 20.11.2026

Пользователь подтвердил APK0.5.2 на Samsung S25 (Android17/One UI9.0) и разрешил продолжить. При начале рабочее дерево чистое, HEAD `febf7fb`. Сняты22 замечания npm audit через проверенные overrides glob/minimatch с сохранением старого callback API ветки Babel/Jest. Финальный audit0, чистая установка и npm ls проходят. Прямые зависимости и36 нативных пакетов сохранили версии. Добавлены5 тестов поведения инструментов и audit-gate moderate+ в CI с сохранением JSON. Прошли90 мобильных тестов, TS/lint, онлайн Expo check, export обеих ОС и native config Android/iOS. Новый APK не собирался. [Решение, проверки и файлы](mobile_release.md#зависимости-и-ci--20112026).

Проверки RuStore/APNs, iOS и общего пилота остаются открытыми. Сервер, commit и git push не менялись. Блок9 не начат.

## Блок 8 — сборка, CI и локальный пилотный прогон, 19.11.2026

Подготовлен APK 0.5.2/code10 после пяти patch-обновлений Expo, RN остаётся 0.88.1. Подпись совпадает с 0.5.1, проверены package/SDK/permissions/backup, встроенные JS/API origin, ZIP и 25 ELF-библиотек на 16 КиБ, SHA-256 b195a31c3119e3621583585ee13183a7956141f9d63adae2a7ae5dadb4cd7bdb. Проверка APK обязательна в сборочном скрипте, отчёт сохраняется в CI. Добавлен изолированный benchmark библиотеки с очисткой вымышленных аккаунтов и защитой от рабочих БД. 5 аккаунтов по 200 материалов, 300 запросов с параллельностью 5, ошибок 0, p95 финального прогона 123.21 мс одновременно со сборкой. Это локальный ориентир, не ёмкость стенда.

Прошли 808 backend-тестов, 90 мобильных, TypeScript/lint, онлайн Expo dependency check, экспорт JS Android/iOS, native config без extension/с App Group, миграция upgrade/check/downgrade/upgrade/check и отдельные 14 проверок инструментов. GitHub Actions ещё не запускался. npm audit оставляет 22 moderate, 0 high/critical. Приёмка обновления на S25 (Android 17 / One UI 9.0 по ответу пользователя), iOS и RuStore/APNs открыты. Серверный push блока 7 сохранён в рабочем дереве. Стенд, коммит и git push не менялись. [Отчёт, файлы, артефакты и процедура выпуска](mobile_release.md).

## Подготовка блока 8 и перенос проверок RuStore, 19.11.2026

Пользователь разрешил двигаться дальше и проверить реальную RuStore-интеграцию при общем тестировании. Подготовлен [протокол](mobile_release_checklist.md) с отдельными задачами реализации, внешними зависимостями, 14 сценариями push и общей регрессией. Блок 7 остаётся частично реализованным. SDK/навигация/APNs ещё требуют разработки. Push выключен, модерация/публикация и новый rollout не выполнялись и отдельно согласуются. План и правила мобильной работы обновлены.

## Блок 7 — Push, подготовка 19.11.2026

Пользователь подтвердил работу 0.5.1 на S25 после обновления Caddy блока 6 и разрешил продолжить. Выбран RuStore Push. Подготовлены устройства, журнал доставок, TTL, повторы, отключение невалидных токенов и отвязка при отзыве сессии. Feature flag выключен. Проект RuStore пока отсутствует. В официальной RN-обёртке выявлены несовместимость сигнатуры с RN 0.88 и ограничение восстановления перехода после завершения процесса. Мобильное подключение, APNs, реальная доставка и новый APK остаются открытыми. Стенд не менялся. [Состояние и подготовка ресурсов](mobile_push.md).


## Блок 6 — настройки, прогресс и данные, 18.11.2026

Пользователь подтвердил работу очереди и разрешил продолжить. Подготовлены мобильные настройки, прогресс, управление напоминанием, смена пароля, экспорт и удаление аккаунта. Используются существующие FastAPI API. В репозитории расширены маршруты Caddy. Прошли 769 backend и 90 mobile тестов, TypeScript, lint, экспорт JavaScript обеих платформ и локальная проверка Caddy. APK 0.5.0/code8 собран и проверен. По замечанию пользователя в 0.5.1 управление напоминаниями перенесено в настройки аккаунта с выбором материала. По отдельному согласованию Caddy обновлён. Выгрузка, настройки, напоминания и управление аккаунтом прошли публичный HTTPS-прогон с двумя вымышленными аккаунтами. Проверки на устройствах открыты. [Протокол блока 6](mobile_testing.md#блок-6--настройки-прогресс-и-данные-18112026)


Изменения блока 6 включают `mobile/src/app/preferences.tsx`, вкладки `progress.tsx` и `settings.tsx`, карточку материала, компоненты `mobile/src/account/`, авторизованный транспорт, очистку SQLite и проверку состояния импорта inbox. Расширены `deploy/Caddyfile.staging`, проверки Caddy и мобильные тесты. Документы обновлены в `docs/`, `mobile/README.md` и `other/mobile_context.md`.

## Блок 5 — кэш, очередь и «Поделиться», 18.11.2026

Пользователь принял 0.3.1 на S25 и разрешил продолжение. Готовы SQLite-кэш, очередь и входящие, безопасный повтор с тем же UUID, новая проверка версии при мобильном PATCH, Android share и iOS App Group inbox. Локальный HTTPS-прогон подтвердил проверку версии и один результат при потерянном ответе. По отдельному согласованию публичный стенд обновлён до блока 5. Резервная копия восстановлена в проверочную БД, миграция применена, FastAPI и Caddy обновлены. Публичный HTTPS-прогон прошёл. Отправка ранее созданной очереди на S25 и прогон на iPhone остаются открытыми. [Приёмка блока 5](mobile_testing.md#блок-5--офлайн-очередь-кэш-и-поделиться)

Исходные изменения блока 4 сохранены в локальном игнорируемом патче `other/mobile_block4_handoff.patch`. HEAD остаётся `3cede9c`.

Изменены API материалов и миграция в `app/` и `migrations/`, маршруты в `deploy/Caddyfile.staging`, клиентские экраны и SQLite-очередь в `mobile/src/`, iOS Share Extension и модуль импорта в `mobile/plugins/` и `mobile/modules/`, проверки backend, мобильного клиента и Caddy.

## Блок 4 — онлайн-библиотека, 18.11.2026

В мобильном приложении готовы поиск, фильтры, сортировка, страницы, карточка, ссылки и заметки, редактирование, категории, статусы, удаление и открытие оригинала. В репозитории обновлена закрытая конфигурация proxy. Локальный HTTPS-прогон подтвердил общий цикл с сайтом, CSRF и изоляцию двух аккаунтов. APK 0.3.0 подготовлен для Samsung S25. Обновлён публичный Caddy и пройден сквозной HTTPS-прогон с двумя вымышленными аккаунтами. На S25 подтверждены сохранение материала и счётчик открытий. В APK 0.3.1 управление категориями доступно вверху библиотеки. На S25 остаётся проверить новое расположение кнопки и сценарии из протокола. Приёмка на iPhone открыта. [Проверки и артефакт](mobile_testing.md#блок-4--онлайн-библиотека-apk-030)

Файлы блока 4:

- Экраны и модель в `mobile/src/app/(tabs)/{_layout,index,settings}.tsx`, `mobile/src/app/_layout.tsx`, `mobile/src/app/library/{[id],categories}.tsx`, `mobile/src/library/{model.ts,ui.tsx}` и `mobile/src/components/ui.tsx`.
- Транспорт и версия в `mobile/src/auth/{api,controller}.ts`, `mobile/app.config.ts`, `mobile/package.json`, `mobile/package-lock.json` и `deploy/Caddyfile.staging`.
- Тесты в `mobile/tests/{authController.test.ts,libraryApi.test.ts,libraryScreen.test.tsx}`, `tests/test_mobile_library.py` и `scripts/check_mobile_gateway.py`.
- Документы `docs/{api,architecture,mobile_auth,mobile_testing,progress,staging}.md`, `mobile/{AGENTS,README}.md` и локальный `other/mobile_context.md`.

В `other/mobile_block3_handoff.patch` сохранён исходный diff блока 3 от `3cede9c`, включая версии 0.2.1/0.2.2 и прежний протокол. Файл локальный и игнорируется Git.

18.11.2026 на Samsung S25 подтверждены регистрация и вход в APK 0.2.2 через внешний HTTPS закрытого стенда. Проверка пароля шлюза перед сохранением и обработка ответа исправлены. Android APK собран, TypeScript, lint и 67 мобильных тестов прошли. Перечень оставшихся проверок устройства и история исправлений приведены в [протоколе](mobile_testing.md). Эта запись относится к передаче работы перед блоком 4.

## Блок 3 — auth/session, 17.11.2026

Пользователь подтвердил установку/работу каркаса0.1 на Samsung S25 и разрешил коммит + следующий блок. Созданы `36bacc1` (staging/capture/egress) и `23b8a5f` (mobile shell). Код блока3, тесты/документация сохраняются отдельным коммитом. **Private API и APK0.2 готовы; публичная/device/iOS приёмка открыта. Блок4 не начат.**

- [x] Единые account/password/consent/rate limits, отдельные web/mobile сессии и native namespace. Cookie/Bearer не подменяют друг друга; mixed не имеет fallback, web-CSRF сохраняется. Hash-only opaque tokens, idle14/absolute60days/10total. Reset отзывает все, change-password сохраняет текущую сессию обоих типов. NoStore/validation без password/token input.
- [x] Миграция k2a4b6c8d0e1: defaultweb/check web-mobile; данные/старые web-сессии сохранены; downgrade отзывает mobile, чтобы старый код не принял их как cookie. Реальные upgrade/downgrade/upgrade/schema parity и миграционные сценарии проходят.
- [x] Mobile0.2/code2: login/register/consent/account/forgot/reset/verify, SecureStore+origin binding+installation cache marker, проверка сервера при запуске/foreground, offline/gateway401/API401 разделены, известный401 не оставляет authenticated UI даже при failed wipe. Remote logout + явно выбранный local-only вариант. Token не в React state/router; one-time URL только в памяти30min с correlationid, без сырого query/fragment в navigation. Callback старого confirm не уничтожает новый link; post-confirm cleanup/refresh failure не объявляет серверную операцию неуспешной.
- [x] Android/iOS association config и два metadata endpoints при явных cert/team; прежние web fallback страницы. Caddy native gate через X-Staging-Authorization для /mobile/*, Bearer сохраняется, пароль шлюза удаляется. API/приложение не используют CookieJar/Origin имитацию. В staging маршрутизация common native resources вне/mobile/* — задача подключения библиотеки блока4.
- [x] **764 Python/API passed in66.89s** в отдельной временной PG16; реальные Alembic entrypoint и schema comparison прошли. Первый757pass/4fail исправлен:2testharness SECRET_KEY,2historicalmigrationfixture предполагалиhead; assertions не ослаблялись, fixture теперьpinnedj1 и есть отдельныйk2test.
- [x] **64 mobile tests/9suites passed2.236s**, tsc/lint, экспорт JS/Hermes обеих ОС, native prebuild/config assertions (включая hostpaths/associatedDomains/backupfalse). Native mocks не заменяют реальные Keystore/Keychain/OS links.
- [x] APK0.2: `mobile/artifacts/teleiosis-0.2.0-android-arm64-preview.apk`,30154531байт,SHA256 `040f2e94adb97e6d7bdb26b1c72b0804bf868ebfb9da80b20996697cf2488d44`. Полная сборка13m45s + финальная JS-инкрементальная38s (785tasks,25executed). apksigner v2 Android Debug/cert совпадает с0.1; manifest API24/target36/compile37/arm64/code2, zipalign-P16, JS и отсутствие env/keyfiles проверены. Store signing/публикации нет.
- [x] Реальный изолированный Caddy HTTPS-test: gateway bypass rejection, Basic/Bearer isolation, anonymous mobile, browser compatibility, metadata без gateway и privatepaths404. Harness добавлен в backendCI; mobileCI проверяет default/configured native associations. GitHub workflow ещё не запускался.
- [x] До rollout server backup `/var/lib/teleiosis/backups/mobile-auth-before-20261117.dump`0600, restore в `teleiosis_restore_test_mobile_20261117` (j1,0users/0contents). Новый image `teleiosis:mobile-auth-20261117`, id`sha256:0797aa153c2124ad89fba512ec0b9ea2edcff980645fdc779a021a437c6b4883`; прежний сохранён. Env rollback snapshot только на сервере0600. Миграция/API/worker/private proxy обновлены, всё ещё **127.0.0.1:8443**, preview CA/volumes отдельные, APP_ENVstaging/EMAIL_BACKENDcapture, egress present.
- [x] Private HTTPS **реальный API**: register/login/session, native-token-as-cookie/web-token-as-Bearer/mixed rejection, captured verify/reset, one-time reuse rejection, глобальный session revoke иlogout; собственный синтетический аккаунт/MIME удалены. Дополнительно полноценный web smoke прошёл библиотеку/категории/verify/reset, реальный worker reminder+digest, stats/export/delete/cleanup. Association JSON без gateway через проверенный CA соответствует cert APK.
- [ ] Public HTTPS/ACME для домена ещё не запущен, SMTP не доставляет в реальные ящики. На S25 подтверждён только0.1: 0.2/session restore/share/SecureStore/reinstall/verified App Links/ошибки сети ещё не проверены. Mac/iPhone/team/accounts остаются внешними зависимостями; iOS binary и production share/push не доказаны.
- [ ] 22moderate npm advisories при установке: force со сменой/понижением SDK не применялся. Продуктовая библиотека/очередь/push, согласованный юридический текст, retention и off-VM backup остаются отдельными работами.

Контракт, сборка, открытая приёмка и rollback: [mobile_auth.md](mobile_auth.md). При откате сначала отозвать mobile-сессии, не возвращать старый cookie-код поверх активных mobile tokens. Публичный proxy — только после согласования режима по [staging.md](staging.md); до этого APK не может войти с телефона в loopback API. По завершении этой подготовки остановиться на review; библиотека блока4 требует отдельного подтверждения.


<details>
<summary>Файлы блока 3</summary>

```text
.github/workflows/backend.yml
.github/workflows/mobile.yml
README.md
app/config.py
app/csrf.py
app/deps.py
app/main.py
app/models.py
app/routers/account.py
app/routers/app_links.py
app/routers/auth.py
app/routers/mobile_auth.py
app/sessions.py
deploy/.env.example
deploy/.env.staging.example
deploy/Caddyfile.staging
deploy/compose.yml
docs/api.md
docs/architecture.md
docs/database.md
docs/decisions.md
docs/mobile_auth.md
docs/mobile_plan.md
docs/mobile_testing.md
docs/progress.md
docs/setup.md
docs/staging.md
migrations/versions/k2a4b6c8d0e1_mobile_sessions.py
mobile/.env.example
mobile/README.md
mobile/app.config.ts
mobile/package-lock.json
mobile/package.json
mobile/scripts/build-android-preview.sh
mobile/scripts/check-native-config.py
mobile/src/app/(tabs)/index.tsx
mobile/src/app/(tabs)/settings.tsx
mobile/src/app/+native-intent.ts
mobile/src/app/_layout.tsx
mobile/src/app/account.tsx
mobile/src/app/email-action.tsx
mobile/src/app/reset-password.tsx
mobile/src/app/sign-in.tsx
mobile/src/app/staging-access.tsx
mobile/src/auth/api.ts
mobile/src/auth/config.ts
mobile/src/auth/context.tsx
mobile/src/auth/controller.ts
mobile/src/auth/emailLinks.ts
mobile/src/auth/vault.ts
mobile/src/components/ui.tsx
mobile/tests/authApi.test.ts
mobile/tests/authController.test.ts
mobile/tests/authVault.test.ts
mobile/tests/emailActionScreen.test.tsx
mobile/tests/emailLinks.test.ts
mobile/tests/signInScreen.test.tsx
scripts/check_mobile_gateway.py
scripts/smoke_mobile_auth.py
tests/test_email_auth_migration.py
tests/test_mobile_app_links.py
tests/test_mobile_auth.py
tests/test_mobile_sessions_migration.py
other/mobile_context.md (ignored, локальный контекст)
```

</details>

## Блок 2 — мобильный каркас, 16.11.2026

Пользователь отдельно разрешил переход к mobile. Публичный HTTPS/SMTP блока 1 отложены; приложение сейчас не обращается к API. Подтверждены Samsung S25 с возможностью USB-подключения и отсутствие аккаунтов магазинов. Mac/iPhone/macOS CI и покрытие без GMS пока не подтверждены. **17.11.2026 пользователь подтвердил установку и работу каркаса на S25, разрешил коммит и переход к блоку 3. Полная приёмка платформенных пунктов блока 2 остаётся открытой.**

- [x] mobile/: Expo SDK 58/RN 0.88.1/React 19.3.0, TypeScript, Expo Router, вкладки Библиотека/Прогресс/Настройки, отдельные диагностические экраны. Палитра/иконка из web, Inter/Manrope локально. Нет auth/API/продуктовой библиотеки, персистентной очереди и push.
- [x] Android text/plain share: raw preview без fetch/resolve/открытия URL; PDF только URL, неподдерживаемые вложения не принимаются, явная очистка и ошибки. iOS эксперимент включается только MOBILE_IOS_SHARE_PROBE=1; штатная конфигурация без extension.
- [x] Отдельный SecureStore probe: запись/read-back, чтение после restart, удаление с проверкой отсутствия, device-only keychain service; без настоящих токенов/логирования содержимого.
- [x] TypeScript и lint проходят; **19 тестов в 3 suites** проходят: валидация share, cold/warm route, повтор/очистка/native errors, warm AppState refresh/unsubscribe, storage read-back/delete/errors. Нативные API в этих тестах mocked.
- [x] Expo Doctor **20/20**, SDK dependency check; JS/Hermes export для двух ОС. Сгенерированы Android/iOS и opt-in iOS extension, проверены permissions/backup/отсутствие extension в штатной сборке; затем iOS возвращён к штатной конфигурации. Это не iOS binary/runtime.
- [x] Воспроизводимый helper автономного arm64 APK с тестовой подписью, workflow JS/native-config checks + ручная APK job. GitHub Actions удалённо не запускался. Ключи/нативные папки/артефакты исключены из Git; store signing и облачные Expo-сервисы не подключены.
- [x] APK собран: **BUILD SUCCESSFUL in 6m 50s**, 785 tasks (753 executed/32 up-to-date). `mobile/artifacts/teleiosis-0.1.0-android-arm64-preview.apk`, 30 059 279 байт (~28.7 MiB), SHA-256 `a2ff8aa4755438e2bf6855b1a48b6439ec970f38fc4388dbbe351a00a52944b0`. apksigner подтвердил v2-подпись **Android Debug**; aapt подтвердил ru.teleiosis.mobile.dev/0.1.0/code1, API24/target36/compile37, arm64. zipalign проверил 16-KiB archive alignment (не ELF/runtime-тест); встроены JS и 5 TTF (4 Inter/Manrope + Ionicons), файлы .env/ключей в APK не найдены. Оригинальные лицензии шрифтов включены в офлайн-экран.
- [x] Повторные проверки итоговых исходников: typecheck/lint, **19 passed in 1.803s**, export Android/iOS успешен, generated native config boundaries проходят. SDK Doctor20/20; shell/YAML/lockfile parity/локальные Markdown-ссылки/diff проверены. Backend suite повторно не запускался.
- [x] Установка и запуск каркаса на S25 подтверждены пользователем 17.11.2026.
- [ ] Samsung runtime: навигация/back, настоящий cold/warm share, SecureStore/restart, поворот/крупный шрифт/TalkBack. ADB в итоге запущен, `List of devices attached` пуст: телефон из этой WSL-среды не обнаружен. Отдельный порт15037 ранее истёк по timeout; это не проверка телефона.

Первая APK-попытка остановилась на Maven read timeout, вторая остановлена нами для настройки уже существующего сетевого proxy среды; успешная третья получила React AAR через этот proxy. JDK/SDK/NDK/Gradle и transient Gradle proxy находятся в /tmp, не в исходниках. В итоговом APK нет mic/photo/external-storage/POST_NOTIFICATIONS разрешений; остаются INTERNET, dev-client SYSTEM_ALERT_WINDOW/VIBRATE и библиотечные USE_BIOMETRIC/USE_FINGERPRINT SecureStore (probe не запрашивает биометрию). Это тестовая конфигурация, окончательный manifest пересматривается перед выпуском.
- [ ] iOS build/device и production Share Extension; предложен стандартный Swift compose + App Group inbox без unsupported открытия host app. Нужен отдельный proof на Mac/iPhone до закрытия платформенного риска.
- [ ] Push SDK: официальные исходники RuStore 6.9.1 изучены (commit c23260a660f943d7f09a828a48e5b4d513b21a95); есть старая Gradle/RN инфраструктура и ветка newArchEnabled, совместимость RN 0.88/AGP 9.2.1 не доказана. SDK не подключён; APNs не проверен. Доставка относится к блоку 7.
- [ ] npm audit: 23 позиции (22 moderate/1 low), корневые advisories glob/minimatch/deepmerge в инструментах Expo/Jest. Совместимый audit fix применён; небезопасный force со сменой/понижением SDK/Jest не применялся. Нужен разбор до выпуска.

Изменения mobile-блока: новый mobile/ (код, конфигурация, lockfile, tests, build/check scripts, README, адаптированный AGENTS официального шаблона), .github/workflows/mobile.yml, docs/mobile_testing.md; обновлены README.md, docs/mobile_plan.md, architecture.md, decisions.md, setup.md, progress.md и локальный ignored other/mobile_context.md. app/, web/, миграции, существующие Python-тесты и сервер в этом блоке не менялись; предыдущие незакоммиченные изменения блока 1 сохранены. Python suite повторно не запускался: изменений backend нет; последний серверный результат блока 1 — 741 passed.

Инструкция установки/проверки: [mobile/README.md](../mobile/README.md). Матрица и границы приёмки: [mobile_testing.md](mobile_testing.md). 17.11.2026 разрешён следующий блок 3 (auth); оставшиеся пункты блока 2 сохраняются в матрице и не считаются пройденными.

<details>
<summary>Полный список файлов мобильного блока 2 (без сгенерированных/ignored сборок)</summary>

```text
mobile/.gitignore
mobile/.npmrc
mobile/.nvmrc
mobile/AGENTS.md
mobile/LICENSE
mobile/README.md
mobile/app.config.ts
mobile/assets/android-icon-background.png
mobile/assets/android-icon-foreground.png
mobile/assets/android-icon-monochrome.png
mobile/assets/favicon.png
mobile/assets/icon.png
mobile/assets/splash-icon.png
mobile/eslint.config.js
mobile/jest.config.js
mobile/package-lock.json
mobile/package.json
mobile/scripts/build-android-preview.sh
mobile/scripts/check-native-config.py
mobile/src/app/(tabs)/_layout.tsx
mobile/src/app/(tabs)/index.tsx
mobile/src/app/(tabs)/progress.tsx
mobile/src/app/(tabs)/settings.tsx
mobile/src/app/+native-intent.ts
mobile/src/app/+not-found.tsx
mobile/src/app/_layout.tsx
mobile/src/app/licenses.tsx
mobile/src/app/probe.tsx
mobile/src/app/share-probe.tsx
mobile/src/components/ui.tsx
mobile/src/fontLicenses.ts
mobile/src/platform/share.ts
mobile/src/platform/storageProbe.ts
mobile/src/theme.ts
mobile/tests/share.test.ts
mobile/tests/shareScreen.test.tsx
mobile/tests/storageProbe.test.ts
mobile/tsconfig.json
.github/workflows/mobile.yml
docs/mobile_testing.md
README.md
docs/mobile_plan.md
docs/architecture.md
docs/decisions.md
docs/setup.md
docs/progress.md
other/mobile_context.md (ignored)
```

</details>

## Блок 1 — закрытый staging/capture, 16.11.2026

После вопроса об отсутствии почтового ящика на техническом домене и сообщения «Что дальше» подготовлен явный тестовый режим без внешней доставки. Публичный запуск ещё не выполнен: private preview только на 127.0.0.1:8443, нужен review временных ограничений перед включением домена. Позже пользователь явно разрешил переход к мобильному блоку 2 с этими открытыми зависимостями; это не закрывает приёмку блока 1.

- [x] APP_ENV=staging / EMAIL_BACKEND=capture: HTTPS/Secure-cookie/SECRET_KEY и закрытые docs сохраняются; prod требует SMTP/TLS, console только dev. Overlay принудительно выбирает capture для API/worker/migrate.
- [x] Атомарные MIME-файлы в отдельном capture_mail volume: каталог 0700/uid 10001, файлы 0600, без сети/токенов в логах, отказ при ошибках и мягкий лимит 1000 без удаления старых писем. Чтение только оператором по SSH; нет публичного почтового API/UI.
- [x] Отдельный Basic Auth gateway, пароль/секреты сгенерированы только на сервере (0600), предупреждение о перехвате на `/`, /app/ сохраняет собственную cookie-авторизацию. Gateway Authorization не передаётся API.
- [x] Полный регресс с новым кодом на сервере: **741 passed in 58.47s**. Изолированная временная PostgreSQL, без реальных данных и опубликованных портов; временный тестовый контейнер/сеть удалены после проверки.
- [x] Private HTTPS smoke с проверкой внутреннего CA: gateway/401/предупреждение/private routes, регистрация/категория/материал, verify/reset по приватным MIME-ссылкам и отзыв сессии, реальный worker reminder/digest, stats/export/delete. Синтетический аккаунт и его письма удалены. Первый smoke остановился до записи из-за отсутствующего staging-маркера у шлюзового 401; условие уточнено, маркер обязателен после успешного входа до записи.
- [x] DNS с сервера: A соответствует VM; AAAA и CAA на домене/родителе не найдены. Это не выдача публичного сертификата.
- [x] Итоговый Caddyfile.staging прошёл offline `caddy validate` без сети/выдачи сертификатов; все Compose-профили принудительно staging/capture проверены через закрытый config JSON без вывода секретов. Проверены syntax/diff и 44 локальные ссылки в 15 Markdown-файлах.
- [x] Egress iptables-nft: управляемые DOCKER-USER/INPUT-цепочки, br_netfilter, systemd перед Docker. Реально проверены БД/публичный HTTPS (разрешены), private endpoint на своей bridge-сети и SSH host (отклонены со счётчиками). Cloud metadata не запрашивали; соответствующая deny-строка проверена конфигурационно.
- [x] Backup 0600 создан на сервере, восстановлен в отдельную БД, ревизия j1f3a5b7c9d0 и synthetic marker совпали. Backup fixture удалён из основной staging-БД, restore-БД оставлена для инспекции.
- [x] После restart Docker API ready, worker держит advisory lock, приватный capture работает; собственные firewall-правила сохранены. В основной staging-БД тестовых аккаунтов нет. Хост/SSH/агент Timeweb не перезапускались и не перенастраивались.
- [ ] Публичный запуск proxy на 80/443 и фактический ACME/TLS для teleiosistest.tw1.ru — ещё не выполнены. Preview использует отдельные CA volumes и restart=no.
- [ ] Реальная SMTP-доставка/спам/DNS отправителя, внешняя зашифрованная копия, политика сроков/реальных данных, GitHub Actions remote CI — не считать выполненными. Backup timer пока не включён, полного reboot VM не было.

Файлы этого продолжения: app/config.py, main.py, mailer.py; deploy/compose.yml, compose.sh, compose.staging.yml, .env.staging.example, Caddyfile.staging, egress-iptables.sh, teleiosis-egress.service, docker-egress.conf; .gitignore; tests/test_config.py, test_deployment_api.py, test_mail_capture.py; scripts/smoke_staging.py, captured_mail.py; docs/staging.md и синхронизация README/setup/api/requirements/decisions/mobile_plan/deployment/progress; локальный other/mobile_context.md. web/, зависимости и миграции не менялись.

Следующее конкретное действие после review режима: `TELEIOSIS_STAGING=1 sh deploy/compose.sh up -d --wait proxy`, затем проверить публичный сертификат/HTTP→HTTPS и ограниченный вход. Перед публикацией не отключать TLS/Basic Auth и не объявлять capture внешней доставкой. Подробности: [staging.md](staging.md).

## Мобильное приложение — блок 1, 16.11.2026

Статус: локальная инженерная часть проверена; полный блок не закрыт без ресурсов и серверной приёмки. Пользователь подтвердил начало блока; отдельным ответом сообщил, что хостинг/бюджет/домен/SMTP пока не выбраны. Блок 2 не начат.

Продолжение 16.11.2026: основатель приобрёл пустой сервер Timeweb Cloud в Санкт-Петербурге, подтвердил root и host fingerprint через консоль; авторизованный SSH работает с отдельным ключом из игнорируемой deploy/.ssh/. ОС/ресурсы проверены: Ubuntu 24.04.5, 2 CPU, 3913 МБ RAM, диск 48 ГБ. Скриптом deploy/bootstrap-ubuntu.sh установлены Docker 29.10.0 / Compose 5.7.1 из официального репозитория, исходники без секретов переданы в /srv/teleiosis, образ teleiosis:staging-20261116 собран на сервере. Предустановленный агент Timeweb и SSH не менялись; хост не перезагружался. Постоянное приложение/proxy ещё не запускались. Основатель отдельно ответил «пока нет» про домен и SMTP. Технические реквизиты — локальный other/mobile_context.md, приватный ключ в документы не добавляется.

Серверная проверка в отдельной internal Docker-сети без published ports: **733 passed in 56.19s**. Первый прогон дал 732 passed / 1 failed из-за Docker tmpfs noexec: fake-docker executable тестовой фикстуры не запускался. Повтор с exec только у временного тестового /tmp прошёл полностью; production-настройки не ослаблялись. Реальный scripts/check_migrations.py на другой новой БД: upgrade head → downgrade -1 → upgrade head и schema parity прошли. Source-тесты подключались read-only, секреты и рабочая БД не использовались. Временные серверные контейнер/сеть удаляются после проверки, образ/исходники остаются; remote pytest не приравнивается к запуску GitHub Actions или production-приёмке.

Файлы серверного продолжения: deploy/bootstrap-ubuntu.sh; уточнение deploy/egress.nft.example; README.md, docs/deployment.md, infrastructure_options.md, mobile_plan.md, progress.md и локальный other/mobile_context.md. app/, web/, requirements и миграции в этом продолжении не менялись. После выбора домена/SMTP сначала подготовить конкретный сетевой rollout для iptables-nft, затем публичный HTTPS/почту; блок 2 не начинать.

- [x] Dockerfile и .dockerignore (allowlist), отдельный deploy/compose.yml: API/worker/явные migrate/PostgreSQL/Caddy, private DB без host-порта, непривилегированный API, read-only filesystem, ограниченные логи.
- [x] Init-db: приложение владеет своей БД без superuser; admin-credentials не передаются в API/worker. Старый compose разработки, web/, зависимости и миграции не изменены.
- [x] Production отключает docs/redoc/OpenAPI, SMTP без TLS запрещён; Origin не допускает credentials, SQL-параметры engine скрыты. Добавлен /ready=200/503 без внутренних подробностей, /health сохранён.
- [x] Backup без перезаписи/публикации неполного архива и restore-check только в новую временную БД. Подготовлены пример egress и systemd backup timer; на хост не устанавливались.
- [x] GitHub Actions: Python/настоящий Alembic/контейнер/backup/restore/proxy/restart на синтетических данных, без автодеплоя. Remote workflow не запускался.
- [x] Локально: `pytest -q` — **733 passed in 36.92s** на отдельном PostgreSQL-контейнере; рабочая teleiosis_db не использовалась. Первый запуск внутри сетевой песочницы завис и был остановлен; успешные прогоны выполнены с разрешённым доступом к одноразовой БД.
- [x] Образ teleiosis:block1-check собран с текущими pinned requirements; контейнеры API/worker стартовали. Настоящий `scripts/check_migrations.py`: upgrade head → downgrade -1 → upgrade head, сравнение моделей/схемы пройдено на отдельной пустой БД. Данные существующего пользователя/материала дополнительно проверяются migration-тестами suite.
- [x] Production HTTP smoke: /ready, закрытые docs, регистрация, сохранение/список синтетической заметки, CSRF-отказ. Контейнер uid=10001, admin-credentials отсутствуют в его окружении.
- [x] Backup/restore: ревизия j1f3a5b7c9d0, один синтетический пользователь и материал восстановлены; контрольный текст сверён. Роль приложения проверена как non-superuser.
- [x] Caddy validate пройден без сети/выпуска сертификатов. Локальный HTTPS на 127.0.0.1 с внутренним CA: сертификат проверен, /health и сайт доступны, HSTS есть, docs/redoc/OpenAPI/ready закрыты. Это не публичный сертификат и не проверка домена РФ.
- [x] После restart API отвечает /ready, worker снова удерживает singleton advisory lock. Это не проверка перезагрузки удалённого сервера и не доказательство доставки почты.
- [x] `git diff --check`, синтаксис shell, YAML Compose/workflow и ссылки документации: 14 Markdown-файлов, 36 локальных ссылок без ошибок. Одноразовые контейнеры/сети/тома удалены после проверки; рабочий teleiosis_db не изменялся. Тестовый образ оставлен в локальном Docker cache.
- [ ] Реальный GitHub CI: нет push/remote-запуска в этой сессии; не объявлять зелёным.
- [ ] Российский сервер приобретён и подготовлен; DNS/публичный HTTPS, SMTP-доставка и юридические условия внешнего теста ещё не проверены. Домен и SMTP ожидают выбора основателя.
- [ ] Egress на выбранном хосте: установлен Docker с iptables-nft backend, поэтому исторический native-nft шаблон не применять. Требуется backend-совместимая политика DOCKER-USER/INPUT и проверка private/metadata до публичного запуска; политика ещё не устанавливалась.
- [ ] Backup timer на сервере: шаблон подготовлен, не установлен; systemd-analyze в текущей среде сообщил об отсутствующем docker.service. Расписание/сроки хранения/внешние зашифрованные копии требуют подтверждения.

Файлы блока 1: Dockerfile, .dockerignore, .gitignore; app/main.py, config.py, db.py; .github/workflows/backend.yml; deploy/compose.yml, Caddyfile, .env.example, init-db.sh, compose.sh, backup.sh, restore-check.sh, egress.nft.example, teleiosis-backup.service/.timer; scripts/check_migrations.py; tests/test_config.py, test_deployment_api.py, test_deployment_scripts.py; docs/deployment.md, infrastructure_options.md и обновления README/архитектуры/API/плана/требований/решений/setup/progress; локальный other/mobile_context.md.

Runbook: [deployment.md](deployment.md). Варианты без покупки: [infrastructure_options.md](infrastructure_options.md). Следующий шаг в том же блоке 1 — подтвердить бюджет/регион/домен/SMTP, затем подготовить конкретный серверный rollout. Не переходить к блоку 2 по факту локального успеха.

## Мобильное приложение — блок 0, 16.11.2026

- [x] Пользователь утвердил план после аудита и разрешил сохранить other/mobile_context.md и начать работу.
- [x] Зафиксированы ответы: РФ, мобильное ядро, кэш и очередь новых URL/заметок; PDF-файлы, обучение, ИИ и подписка позже.
- [x] Локальный закрытый тест веб-MVP проведён без критических ошибок по сообщению пользователя; серверного деплоя не было.
- [x] Сохранён локальный контекст в other/mobile_context.md (папка игнорируется Git, правила не менялись).
- [x] Подготовлены docs/mobile_plan.md и docs/architecture.md: блоки 0–13, границы релиза, сессии, очередь/share, каналы, совместимость и реестр ресурсов.
- [x] Добавлена приёмочная матрица M01–M20; обновлены README, requirements, decisions, api и setup. Матрица описывает будущие проверки, не пройденные mobile-тесты.
- [x] Проверены локальные Markdown-ссылки, границы документальных изменений и git diff --check; app/, web/, зависимости и миграции не изменены. Python/mobile runtime-тесты не запускались для изменения документации; результаты прежних запусков не переиспользуются как новые.
- [ ] Внешние ресурсы подтверждены: бюджет/хостинг/домен/SMTP, юридическая схема, macOS/устройства/аккаунты, магазины/покрытие push. Реестр R1–R7 — mobile_plan.md. Минимальные ОС фиксируются после проверки SDK в блоке 2.
- [ ] Полная приёмка блока 0: документальная часть подготовлена, перечисленные входные условия остаются открытыми. Не считать отсутствие ответа подтверждением.
- [x] Получено отдельное подтверждение начала блока 1. В самом блоке 0 установки, деплой, БД и мобильный код не менялись; результаты следующего блока выше.

Мобильные блоки не заменяют историческую нумерацию MVP ниже. Внешние входные условия блока 0 перенесены явно открытыми в подтверждённый блок 1; это не разрешение молча выбрать провайдеров или купить услуги.

## Очистка после MVP — 15.11.2026
- [x] Удалены бот, Telegram Mini App, initData и Bearer-вход; остались e-mail/пароль и cookie-сессии.
- [x] Общие тесты переведены на e-mail-аккаунты и cookie с Origin; зависимости бота удалены из requirements.txt.
- [x] Подготовлена миграция j1f3a5b7c9d0: обязательный e-mail, удаление telegram_id/username; аккаунты без e-mail блокируют миграцию без потери данных.
- [x] Проверка: 718 тестов прошли, включая установку схемы с нуля, сохранение данных, downgrade/upgrade и отказ для аккаунтов без e-mail; импорты API/воркера/метрик проверены без пакетов бота.
- [ ] Применить миграцию к рабочей базе после резервного копирования и проверки старых аккаунтов.
- Дизайн и other не изменялись. Этапы ниже отражают историю разработки.

## Этап 1. Фундамент — завершён

- [x] 1.1 Окружение: Python, Git, VS Code, GitHub
- [x] 1.2 Структура проекта, .venv, .gitignore, .env.example
- [x] 1.3 Git и приватный репозиторий на GitHub
- [x] 1.4 FastAPI-каркас, эндпоинт /health, requirements.txt
- [x] 1.5 Первые документы в docs

## Этап 2. База данных — завершён
- [x] 2.1 PostgreSQL в Docker
- [x] 2.2 Проектирование схемы (docs/database.md)
- [x] 2.3 SQLAlchemy-модели
- [x] 2.4 Миграции Alembic
- [x] 2.5 Тесты схемы (pytest, отдельная БД teleiosis_test)

## Этап 3. Backend API (ядро) — завершён
- [x] 3.1 Структура API, get_db, временная идентификация (DEV_AUTH_ENABLED)
- [x] 3.2 API категорий, изоляция данных
- [x] 3.3 Сохранение материалов, нормализация URL, защита от дублей
- [x] 3.4 Список: поиск, фильтры, сортировка, пагинация
- [x] 3.5 Изменение и удаление, правила статусов
- [x] 3.6 Метаданные ссылок, защита от SSRF

## Этап 4. Telegram-бот — завершён
- [x] 4.1 Каркас бота (aiogram), вход бота в API по ключу, /start, прокси для Telegram
- [x] 4.2 Приём ссылок, обработка дублей
- [x] 4.3 Пересланные сообщения и заметки (/note)
- [x] 4.4 Кнопки статуса и категории, /category

## Этап 5. Безопасность и авторизация Mini App — завершён
- [x] 5.1 Проверка подписи Telegram initData (app/telegram_auth.py)
- [x] 5.2 Таблица сессий auth_sessions, решение по токенам
- [x] 5.3 Эндпоинт POST /auth/telegram
- [x] 5.4 Вход по Bearer-токену в get_current_user
- [x] 5.5 Тесты переведены на Bearer-токены
- [x] 5.6 Dev-вход удалён

## Смена курса (08.11.2026)
- [x] Решение: MVP как веб-сайт, мобильные приложения после тестирования; Mini App отменён, бот и вход по initData заморожены
- [x] Бизнес-план v2
- [x] Технический план v2
- [x] Документы в docs и README
- [x] Архитектурные решения этапа 6 (вход, сессия, фронтенд, быстрое сохранение)

## Этап 6. Веб-сайт MVP — завершён
- [x] 6.1 Миграция users (e-mail, пароль, согласие, telegram_id необязателен)
- [x] 6.2 Пароли (Argon2id) и регистрация
- [x] 6.3 Вход, выход и сессия в cookie, проверка Origin
- [x] 6.4 Ограничение частоты запросов
- [x] 6.5 Сброс пароля
- [x] 6.6 Каркас сайта и страницы входа
- [x] 6.7 Библиотека и быстрое добавление
- [x] 6.8 Карточка, статусы, удаление, фиксация открытий
- [x] 6.9 Категории
- [x] 6.10 Проверка на телефоне и десктопе, закладка браузера

## Этап 7. Напоминания и статистика — завершён
- [x] 7.0 Архитектурные решения (decisions.md от 10.11.2026), tzdata в requirements.txt
- [x] 7.1 Синхронизация docs (api, database, requirements, setup)
- [x] 7.2 Миграция users.last_digest_on, настройки пользователя (PATCH /me/settings), часовой пояс при регистрации
- [x] 7.3 Подтверждение e-mail
- [x] 7.4 Экран «Настройки», смена пароля
- [x] 7.5 Статистика (/stats), страница «Прогресс», строка над библиотекой
- [x] 7.6 Почта: send_email возвращает bool, SECRET_KEY, отписка
- [x] 7.7 Воркер и ежедневная подборка
- [x] 7.8 Напоминания по материалу
- [x] 7.9 Метрики для закрытого тестирования

## Этап 8.0. Редизайн-лайт — завершён
- [x] R1 Дизайн-токены в app.css
- [x] R2 Кнопки, поля, фокус, область нажатия 44 px
- [x] R3 Шапка и навигация
- [x] R4 Библиотека: карточки, чипы, пустые состояния
- [x] R5 Карточка материала и «Прогресс»
- [x] R6 Страницы входа
- [x] R7 SVG-иллюстрации и микроанимации (режется первой, если не успеваем)
- [x] R8 Итоговая проверка и документация

## Этап 8.1. Выгрузка данных и удаление аккаунта — завершён
- [x] 8.1a Выгрузка данных (GET /me/export)
- [x] 8.1b Удаление аккаунта (backend)
- [x] 8.1c Кнопки «Скачать данные» и «Удалить аккаунт» в настройках

## Этап 8.2. Документ с тарифами — завершён
- [x] docs/pricing.md

## Этап 8.3. Подготовка к деплою — не начат
- [ ] Ответы основателя: хостинг в РФ, домен, почтовый провайдер, бюджет, где проводить закрытый тест
- [ ] План деплоя (HTTPS, прокси, HSTS, закрытие /docs, секреты, SMTP, SPF/DKIM/DMARC, бэкапы, ограничение исходящих соединений)

## Ближайшие этапы
- [ ] Закрытое тестирование
- [ ] Юрист: согласие, политика, 152-ФЗ, ФЗ-38, Роскомнадзор, состав выгрузки, резервные копии
- [ ] Лендинг welcome.html (L1-L4) после закрытого теста
