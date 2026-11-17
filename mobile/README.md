# Телеосис: мобильное приложение

Блоки 2/3 утверждённого [плана](../docs/mobile_plan.md). В 0.2.0 добавлены вход/регистрация, восстановление/подтверждение, защищённая сессия и профиль. Backend и веб-MVP сохраняются; библиотека, офлайн-очередь и push — следующие блоки. [Контракт, проверки и открытая приёмка auth](../docs/mobile_auth.md).

## Стек и запуск

- Node.js 22.23.5 (`.nvmrc`), npm и зафиксированный `package-lock.json`.
- Expo SDK 58, React Native 0.88.1, React 19.3.0, TypeScript, Expo Router, Hermes/New Architecture.
- Предварительный технический минимум SDK: Android 7/API 24, iOS 16.4. Это не обещание поддержки до испытаний на устройствах. Android compile SDK 37/target 36, Build Tools 37.0.0; минимальный Xcode по матрице Expo — 26.4.
- Палитра и иконка из web/, Inter и Manrope упакованы в приложение через npm-пакеты Expo Google Fonts; во время работы шрифты из интернета не загружаются. Оригинальные лицензии шрифтов доступны офлайн в Настройки → «Лицензии шрифтов» (src/fontLicenses.ts).

```sh
cd mobile
npm ci
# Только публичные настройки, без паролей/токенов:
cp .env.example .env
npm run typecheck
npm run lint
npm test
npm run check:dependencies
npm run export:check
```

`export:check` собирает JS/Hermes для двух платформ, **не APK/IPA**. `npx expo-doctor` проверяет конфигурацию. Для разработки нужны установленные development builds; Expo Go не подтверждает работоспособность входящего share.

```sh
npm run android
# На Mac с Xcode/CocoaPods:
npm run ios
# Metro для уже установленного development build:
npm start
```

Нативные папки android/ и ios/ генерируются через CNG и исключены из Git. Изменения делаются в app.config.ts и config plugins. Изменение нативной конфигурации требует пересборки. Тестовые идентификаторы `ru.teleiosis.mobile.dev` / `teleiosis-dev` не резервируют production-ID в магазинах. EAS/Expo Push/OTA/аналитика не настроены; облачные сборки и публикация автоматически не запускаются.

## Автономный APK для Samsung S25

Нужны JDK 17, Android SDK command-line tools, переменные JAVA_HOME/ANDROID_HOME и принятые лицензии SDK. Имена пакетов в текущем SDK repository:

```sh
sdkmanager 'platform-tools' 'platforms;android-37.0' 'build-tools;37.0.0' 'ndk;27.1.12297006'
EXPO_PUBLIC_API_ORIGIN=https://teleiosistest.tw1.ru EXPO_PUBLIC_STAGING_GATE=1 sh scripts/build-android-preview.sh
```

Результат: `artifacts/teleiosis-0.2.0-android-arm64-preview.apk` и SHA-256 в выводе. Это arm64-сборка с упакованным JS, работающая без Metro и сервера. Gradle-вариант Release использует **тестовый debug key шаблона**: APK предназначен для локальной проверки, не для магазина. Нет production signing key, IPA или AAB. Файлы сборок и ключи исключены из Git. Окончательную подпись и приложение магазина готовим в блоке выпуска.

Локальная сборка 17.11.2026: 30 154 531 байт, SHA-256 `040f2e94adb97e6d7bdb26b1c72b0804bf868ebfb9da80b20996697cf2488d44`. Проверены v2 Android Debug signature (тот же сертификат, что 0.1), API24/target36/arm64, встроенный JS и 16-KiB archive alignment. Typecheck/lint, 64 теста, экспорт обеих ОС и association config проходят. Установка 0.1 на S25 подтверждена; 0.2 ещё не проверена на телефоне. Публичный API пока выключен: вход с телефона проверяется после согласованного HTTPS-запуска, пароль шлюза вводится отдельно в приложении. Миграция/приватный API/smoke готовы: [mobile_auth.md](../docs/mobile_auth.md).

Можно скопировать APK на телефон и открыть для установки либо при работающем USB/ADB:

```sh
adb devices
adb install -r artifacts/teleiosis-0.2.0-android-arm64-preview.apk
```

Для WSL2 проброс USB из Windows настраивается отдельно; наличие телефона не означает его видимость внутри WSL. Запуск из IDE не заменяет тест автономного APK. При несовпадении подписи обновление существующей установки не пройдёт; удаление приложения стирает его данные, поэтому не делать его автоматически.

## Что проверять на устройстве

Записывать модель, версию ОС, версию APK/хеш и результат каждого пункта в [протокол](../docs/mobile_testing.md). Установка/запуск 0.1 подтверждены на S25; специальные runtime-пункты и 0.2 ещё открыты.

1. Открыть приложение; переключить Библиотеку → Прогресс → Настройки; открыть «Проверить устройство» и вернуться системной кнопкой/жестом.
2. Проверка устройства → «Записать и проверить». Закрыть приложение, снова открыть → «Прочитать после перезапуска». Удалить запись; чтение должно подтвердить её отсутствие. Используется только отдельный несекретный маркер, не токен аккаунта.
3. Из браузера поделиться одной http/https-ссылкой, затем выделенным текстом. Повторить с закрытым приложением и при уже открытом. Должен открыться экран «Входящий материал», полный текст сохранён в предпросмотре.
4. «Очистить и закрыть»; открыть экран входящего материала вручную — данных нет. Поделиться тем же текстом повторно: это новый видимый приём, а не подавленный дубль.
5. Отменить системное меню «Поделиться» до выбора приложения — приложение не меняется. Проверить поворот, увеличенный системный шрифт и TalkBack; экран прокручивается, кнопки доступны.
6. Повторить при выключенной сети: каркас, share-предпросмотр и SecureStore не требуют сервера. Это **не** доказательство офлайн-очереди: материал никуда не сохраняется и может быть потерян при завершении процесса.

Для изоляции обработки Android intent от поведения браузера можно использовать:

```sh
adb shell am start -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT 'https://example.com/book.pdf' -p ru.teleiosis.mobile.dev
```

В логи и отчёты не копировать содержимое личных share-пакетов. Отладочные сообщения приложения не выводят их. Экран читает сырые getSharedPayloads, не вызывает resolve/fetch и не открывает URL автоматически. Файлы и несколько вложений не поддерживаются; PDF допускается только как URL. Ограничение 20 000 символов относится исключительно к исследовательскому экрану и не устанавливает продуктовый API-контракт.

## iOS share и безопасное хранилище

Входящий expo-sharing экспериментальный. По умолчанию iOS Share Extension **выключена**, Android text/plain включён. Для отдельного исследования на Mac:

```sh
MOBILE_IOS_SHARE_PROBE=1 npx expo prebuild --platform ios --no-install
MOBILE_IOS_SHARE_PROBE=1 npm run ios
```

App Group/подпись для extension требуют соответствующей настройки Apple. Эксперимент Expo открывает основное приложение из extension способом, который Apple официально не поддерживает. Такую сборку не считать готовой к App Store. Предлагаемый production-путь — обычная Swift Share Extension со своим compose UI и записью черновика в общий App Group inbox, без принудительного открытия основного приложения; интеграция inbox с очередью — блок 5. Прежде чем закрыть блок 2, нужно проверить этот путь на Mac/iPhone; реализации пока нет.

Для возврата к штатной конфигурации генерировать iOS без MOBILE_IOS_SHARE_PROBE; проверять отсутствие extension:

```sh
npx expo prebuild --no-install
python3 scripts/check-native-config.py
# В явно включённом варианте:
python3 scripts/check-native-config.py --ios-share-probe
```

SecureStore использует отдельный keychainService и WHEN_UNLOCKED_THIS_DEVICE_ONLY, ошибки не скрываются сообщением об успехе. Проверочная запись не является API-контрактом хранения будущих сессий. Android backup rules исключают SecureStore; на iOS Keychain может переживать удаление приложения. Очистка при выходе/удалении аккаунта и переустановке проектируется в блоках 3/6, отсутствие маркера после удаления iOS-приложения не гарантируется.

## Проверки и незакрытые риски

Автотесты проверяют входные типы/размер, PDF URL, сохранение полного текста, отказ от неподдерживаемых вложений, переход, очистку/повторный share, обновление на warm return, обработку нативных ошибок, read-back и проверку удаления SecureStore. Mocks не доказывают работу Keystore, Keychain или системного share.

CI: `.github/workflows/mobile.yml` — проверки JS и генерации двух нативных проектов; отдельная ручная Android APK-сборка с загрузкой артефакта на 7 дней. Workflow ещё не запускался в GitHub. macOS CI/аккаунты/физический iPhone не подтверждены, iOS binary не собран.

Проверен исходный RuStore Push SDK 6.9.1 (официальный tag, commit `c23260a660f943d7f09a828a48e5b4d513b21a95`): исходники содержат ветку newArchEnabled, но dev-пример опирается на RN 0.72.17, модуль — на ReactContextBaseJavaModule, собственный Gradle classpath 7.2.2/kotlin-android. Совместимость с RN 0.88/AGP 9.2.1 не доказана. SDK не установлен/не инициализирован; нужен отдельный compile/device probe до выбора канала. APNs требует Apple-ресурсов. Google-сервисы для текущего каркаса не нужны; покрытие Android без GMS и дистрибьютор push ещё не согласованы.

На 17.11.2026 npm при установке сообщает 22 moderate позиции в дереве зависимостей инструментов (ранее 23 включая low). Совместимый `npm audit fix` применён, отчёт не обнулился. Предлагаемые force-исправления меняют/понижают SDK или Jest и не применялись. Не объявлять зависимости безопасными или блок 2 принятым до разбора и повторной проверки перед выпуском.

Официальные источники, проверены 16.11.2026: [матрица Expo SDK 58](https://docs.expo.dev/versions/v58.0.0/), [Expo Router](https://docs.expo.dev/router/installation/), [входящий sharing](https://docs.expo.dev/versions/v58.0.0/sdk/sharing/), [SecureStore](https://docs.expo.dev/versions/v58.0.0/sdk/securestore/), [Apple Share Extensions](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/Share.html), [RuStore React Native Push 6.9.1](https://www.rustore.ru/help/sdk/push-notifications/react/6-9-1).
