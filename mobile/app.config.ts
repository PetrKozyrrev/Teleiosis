import type { ExpoConfig } from 'expo/config';

// The experimental iOS extension is confined to explicit investigation builds.
const iosShareProbe = process.env.MOBILE_IOS_SHARE_PROBE === '1';

const config: ExpoConfig = {
  name: 'Телеосис · тест',
  slug: 'teleiosis-mobile',
  version: '0.1.0',
  scheme: 'teleiosis-dev',
  platforms: ['android', 'ios'],
  orientation: 'default',
  userInterfaceStyle: 'light',
  icon: './assets/icon.png',
  ios: {
    bundleIdentifier: 'ru.teleiosis.mobile.dev',
    supportsTablet: true,
    infoPlist: { CFBundleDevelopmentRegion: 'ru', ITSAppUsesNonExemptEncryption: false },
  },
  android: {
    package: 'ru.teleiosis.mobile.dev',
    versionCode: 1,
    blockedPermissions: ['android.permission.RECORD_AUDIO', 'android.permission.READ_MEDIA_IMAGES', 'android.permission.READ_MEDIA_VIDEO', 'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE'],
  },
  plugins: [
    'expo-font',
    'expo-router',
    'expo-dev-client',
    ['expo-secure-store', { configureAndroidBackup: true }],
    ['expo-sharing', {
      android: { enabled: true, singleShareMimeTypes: ['text/plain'], multipleShareMimeTypes: [] },
      ios: {
        enabled: iosShareProbe,
        activationRule: { supportsText: true, supportsWebURLWithMaxCount: 1 },
      },
    }],
    ['expo-build-properties', {
      android: { minSdkVersion: 24 },
      ios: { deploymentTarget: '16.4' },
    }],
  ],
  extra: { iosShareProbe, stage: 'platform-probe' },
};

export default config;
