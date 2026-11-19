This is an Expo/React Native mobile application. Prioritize mobile-first patterns, performance, and cross-platform compatibility.

## Expo has changed — do not trust your training data

Expo ships breaking changes every SDK release. APIs you remember are likely renamed, moved, or removed. Before writing any code that touches an Expo, EAS, or React Native API:

1. Read the major version of the `expo` package in `package.json`.
2. Fetch the matching versioned docs: `https://docs.expo.dev/versions/v<major>.0.0/`
3. For anything else, fetch https://docs.expo.dev/llms.txt — an index of all Expo docs with corrections to common LLM misconceptions. Follow its links to the specific page you need; never answer from memory.

## Commands

Use `bunx` instead of `npx` if the project uses bun (`bun.lock` present).

```bash
npx expo install <package>  # ALWAYS use instead of npm/yarn/pnpm/bun add — resolves SDK-compatible versions
npx expo start              # start the dev server
npx expo lint               # lint
npx tsc --noEmit            # typecheck
npx expo-doctor             # diagnose dependency and config issues
npx expo install --fix      # fix incompatible package versions
```

Run lint and typecheck before declaring any task done.

## Navigation & Routing

- Use **Expo Router** for all navigation. Routes live in `src/app/` — every file there is a screen, `_layout.tsx` files define navigators. Keep non-route code (components, hooks, utils) outside `src/app/`.
- Import `Link`, `router`, and `useLocalSearchParams` from `expo-router`.
- Docs: https://docs.expo.dev/router/introduction.md

## Project build policy

The approved plan uses local development builds and a standalone Android test APK; see README.md and scripts/build-android-preview.sh. Do not connect cloud build, OTA, analytics, push providers, paid services or store publishing without an explicit project decision. iOS requires macOS/Xcode; lack of those resources leaves device acceptance open, rather than implying a successful iOS build.

The user confirmed APK 0.5.1 works after the approved block 6 staging rollout and authorized block 7 on 2026-11-19. Android push provider is RuStore Push. Provider accounts and Apple build resources are not yet available. See ../docs/mobile_push.md for prerequisites and implementation status. On 2026-11-19 the user authorized proceeding with block 8 preparation and deferred real RuStore acceptance to general testing. Track unfinished implementation and deferred checks in ../docs/mobile_release_checklist.md. Block 7 remains incomplete and push stays disabled. Blocks 9–13, store submission/publication, commits, git push, and any new staging rollout require separate approval. Read ../docs/mobile_plan.md and ../docs/mobile_testing.md, update the report and ../other/mobile_context.md, then stop for review.

## Rules

- Preview APK handoff requires a successful `scripts/check_android_apk.py` report with matching SHA-256. Keep `preview-policy.json`, package.json, and app.config.ts versions consistent. Never change the pinned certificate just to make a failing build pass. See ../docs/mobile_release.md for block 8 checks, dependency audit debt, and rollout boundaries.

- If `ios/` and `android/` directories do not exist, they are generated (Continuous Native Generation). Never create or edit them by hand — configure native behavior in `app.json` and config plugins.
- Expo Go only includes its bundled native modules. After adding a library with native code, the app needs a development build: `npx expo run:ios|android` locally, or `eas build --profile development`.
- Prefer recommended Expo modules over third-party libraries, and check your available skills before adding dependencies. Docs: https://docs.expo.dev/versions/latest/index.md
