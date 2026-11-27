import type { ExpoConfig } from 'expo/config';

// Enable the iOS share target for builds with App Group signing.
const iosShare = process.env.MOBILE_IOS_SHARE === '1';
const apiUrl = process.env.EXPO_PUBLIC_API_ORIGIN ? new URL(process.env.EXPO_PUBLIC_API_ORIGIN) : null;
if (apiUrl && (apiUrl.protocol !== 'https:' || apiUrl.username || apiUrl.password || apiUrl.pathname !== '/' || apiUrl.search || apiUrl.hash)) {
  throw new Error('EXPO_PUBLIC_API_ORIGIN must be an HTTPS origin');
}

const config: ExpoConfig = {
  name: 'Телеосис · тест',
  slug: 'teleiosis-mobile',
  version: '0.17.0',
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
    versionCode: 25,
    allowBackup: false,
    intentFilters: apiUrl ? [{ action: 'VIEW', autoVerify: true, category: ['BROWSABLE', 'DEFAULT'], data: [
      { scheme: 'https', host: apiUrl.hostname, path: '/app/reset.html' },
      { scheme: 'https', host: apiUrl.hostname, path: '/app/verify.html' },
    ] }] : [],
    blockedPermissions: ['android.permission.RECORD_AUDIO', 'android.permission.READ_MEDIA_IMAGES', 'android.permission.READ_MEDIA_VIDEO', 'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE'],
  },
  plugins: [
    'expo-asset',
    'expo-file-system',
    'expo-font',
    'expo-router',
    'expo-sqlite',
    'expo-dev-client',
    ['expo-secure-store', { configureAndroidBackup: true }],
    ...(iosShare ? ['./plugins/withShareInbox'] : []),
    ['expo-sharing', {
      android: { enabled: true, singleShareMimeTypes: ['text/plain'], multipleShareMimeTypes: [] },
      ios: {
        enabled: iosShare,
        appGroupId: 'group.ru.teleiosis.mobile.dev',
        activationRule: { supportsText: true, supportsWebUrlWithMaxCount: 1 },
      },
    }],
    ['expo-build-properties', {
      android: { minSdkVersion: 24 },
      ios: { deploymentTarget: '16.4' },
    }],
  ],
  extra: { iosShare, stage: process.env.EXPO_PUBLIC_STAGING_GATE === '1' ? 'staging-auth' : 'auth' },
};

export default config;
