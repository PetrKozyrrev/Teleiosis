import type { ExpoConfig } from 'expo/config';

// The experimental iOS extension is confined to explicit investigation builds.
const iosShareProbe = process.env.MOBILE_IOS_SHARE_PROBE === '1';
const apiUrl = process.env.EXPO_PUBLIC_API_ORIGIN ? new URL(process.env.EXPO_PUBLIC_API_ORIGIN) : null;
if (apiUrl && (apiUrl.protocol !== 'https:' || apiUrl.username || apiUrl.password || apiUrl.pathname !== '/' || apiUrl.search || apiUrl.hash)) {
  throw new Error('EXPO_PUBLIC_API_ORIGIN must be an HTTPS origin');
}

const config: ExpoConfig = {
  name: 'Телеосис · тест',
  slug: 'teleiosis-mobile',
  version: '0.2.0',
  scheme: 'teleiosis-dev',
  platforms: ['android', 'ios'],
  orientation: 'default',
  userInterfaceStyle: 'light',
  icon: './assets/icon.png',
  ios: {
    bundleIdentifier: 'ru.teleiosis.mobile.dev',
    supportsTablet: true,
    associatedDomains: apiUrl ? [`applinks:${apiUrl.hostname}`] : [],
    infoPlist: { CFBundleDevelopmentRegion: 'ru', ITSAppUsesNonExemptEncryption: false },
  },
  android: {
    package: 'ru.teleiosis.mobile.dev',
    versionCode: 2,
    allowBackup: false,
    intentFilters: apiUrl ? [{ action: 'VIEW', autoVerify: true, category: ['BROWSABLE', 'DEFAULT'], data: [
      { scheme: 'https', host: apiUrl.hostname, path: '/app/reset.html' },
      { scheme: 'https', host: apiUrl.hostname, path: '/app/verify.html' },
    ] }] : [],
    blockedPermissions: ['android.permission.RECORD_AUDIO', 'android.permission.READ_MEDIA_IMAGES', 'android.permission.READ_MEDIA_VIDEO', 'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE'],
  },
  plugins: [
    'expo-file-system',
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
  extra: { iosShareProbe, stage: process.env.EXPO_PUBLIC_STAGING_GATE === '1' ? 'staging-auth' : 'auth' },
};

export default config;
