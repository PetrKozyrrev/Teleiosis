#!/bin/sh
# Standalone arm64 test APK. The generated Expo template uses the debug key.
# This helper never creates or handles a store signing key.
set -eu
mobile_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$mobile_dir"
npx --no-install expo prebuild --platform android --no-install
cd android
./gradlew :app:assembleRelease -PreactNativeArchitectures=arm64-v8a \
  --no-daemon --max-workers=2 -Dorg.gradle.jvmargs='-Xmx3g -XX:MaxMetaspaceSize=1g' \
  -Dorg.gradle.internal.http.socketTimeout=300000 -Dorg.gradle.internal.http.connectionTimeout=60000
cd "$mobile_dir"
mkdir -p artifacts
cp android/app/build/outputs/apk/release/app-release.apk artifacts/teleiosis-0.1.0-android-arm64-preview.apk
sha256sum artifacts/teleiosis-0.1.0-android-arm64-preview.apk
