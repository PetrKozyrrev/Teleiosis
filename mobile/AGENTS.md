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

The user confirmed APK 0.5.2 works on Samsung S25 (Android 17 / One UI 9.0) on 2026-11-20 and authorized continuing block 8. Previously the user confirmed APK 0.5.1 works after the approved block 6 staging rollout and authorized block 7 on 2026-11-19. Android push provider is RuStore Push. Provider accounts and Apple build resources are not yet available. See ../docs/mobile_push.md for prerequisites and implementation status. On 2026-11-19 the user authorized proceeding with block 8 preparation and deferred real RuStore acceptance to general testing. Track unfinished implementation and deferred checks in ../docs/mobile_release_checklist.md. Block 7 remains incomplete and push stays disabled. On 2026-11-20 the user accepted APK 0.5.3 on S25 and authorized continuing with block 9A (tags and collections); see ../docs/mobile_organization.md. The user separately approved the 9A API/database rollout; it completed on 2026-11-20 with push disabled and the existing worker/DB/Caddy containers unchanged. The user accepted APK 0.6.0 on S25 on 2026-11-21 and requested a new-chat handoff. Keep the open block 8 dependencies explicit. Blocks 10–13, store submission/publication, commits, git push, and any new staging rollout require separate approval. Read ../docs/mobile_plan.md and ../docs/mobile_testing.md, update the report and ../other/mobile_context.md, then stop for review.


On 2026-11-21 the user authorized local block 9B development. See ../docs/mobile_import_search.md for the contract, preview release and device tests. Staging rollout, commit, push, publication and subsequent blocks require separate approval.


The user accepted the local 9B result and authorized local 9C work on 2026-11-21. See ../docs/mobile_pdf.md. Provider selection, costs, staging rollout, commit, push, publication and block 10 require separate approval.

## Rules

- Preview APK handoff requires a successful `scripts/check_android_apk.py` report with matching SHA-256. Keep `preview-policy.json`, package.json, and app.config.ts versions consistent. Never change the pinned certificate just to make a failing build pass. See ../docs/mobile_release.md for block 8 checks, dependency audit policy, and rollout boundaries.
- After dependency changes run `npm run audit:dependencies` and `npm run test:toolchain` along with lint/typecheck and the mobile suite. Preserve the `test-exclude@6.0.0` glob callback exception until the React Native Babel preset migrates. Do not replace it with the modern glob API without testing that consumer.

- If `ios/` and `android/` directories do not exist, they are generated (Continuous Native Generation). Never create or edit them by hand — configure native behavior in `app.json` and config plugins.
- Expo Go only includes its bundled native modules. After adding a library with native code, the app needs a development build: `npx expo run:ios|android` locally, or `eas build --profile development`.
- Prefer recommended Expo modules over third-party libraries, and check your available skills before adding dependencies. Docs: https://docs.expo.dev/versions/latest/index.md

On 2026-11-22 the user accepted standalone PDF creation on the S25 with 0.8.1 and authorized local block 10. Weekly progress counts completed tasks, with minutes reported separately. See ../docs/mobile_week_plan.md for the candidate, outstanding checks and rollout requirements.
