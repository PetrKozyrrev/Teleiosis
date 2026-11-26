import { Stack } from 'expo-router';
import { useEffect } from 'react';
import { useFonts } from 'expo-font';
import { Inter_400Regular } from '@expo-google-fonts/inter/400Regular';
import { Inter_600SemiBold } from '@expo-google-fonts/inter/600SemiBold';
import { Inter_700Bold } from '@expo-google-fonts/inter/700Bold';
import { StatusBar } from 'expo-status-bar';
import { colors } from '../theme';
import { AuthProvider } from '../auth/context';
import { OfflineSync } from '../offline/sync';
import { clearPdfPreviews } from '../library/pdf';
import { useLanguageReady, useTranslation } from '../i18n';

export default function RootLayout() {
  const t = useTranslation();
  const languageReady = useLanguageReady();
  useEffect(clearPdfPreviews, []);
  const [loaded, error] = useFonts({ Inter_400Regular, Inter_600SemiBold, Inter_700Bold });
  if (!languageReady || (!loaded && !error)) return null;
  return <AuthProvider>
    <OfflineSync />
    <StatusBar style="dark" />
    <Stack screenOptions={{ headerTintColor: colors.primary, headerStyle: { backgroundColor: colors.surface }, contentStyle: { backgroundColor: colors.background } }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="add-link" options={{ title: '' }} />
      <Stack.Screen name="progress" options={{ title: '' }} />
      <Stack.Screen name="library/[id]" options={{ title: t('Материал') }} />
      <Stack.Screen name="library/complete" options={{ title: t('Завершение изучения') }} />
      <Stack.Screen name="library/organization" options={{ title: t('Теги и коллекции') }} />
      <Stack.Screen name="library/organize" options={{ title: t('Теги и коллекции материала') }} />
      <Stack.Screen name="library/goals" options={{ title: t('Добавить к цели') }} />
      <Stack.Screen name="goals/[id]" options={{ title: t('Цель') }} />
      <Stack.Screen name="library/categories" options={{ title: t('Категории') }} />
      <Stack.Screen name="library/import" options={{ title: t('Импорт библиотеки') }} />
      <Stack.Screen name="review" options={{ title: t('Повторение') }} />
      <Stack.Screen name="plan" options={{ title: t('Недельный план') }} />
      <Stack.Screen name="probe" options={{ title: t('Проверка устройства') }} />
      <Stack.Screen name="licenses" options={{ title: t('Лицензии шрифтов') }} />
      <Stack.Screen name="preferences" options={{ title: t('Настройки аккаунта') }} />
      <Stack.Screen name="reading-schedule" options={{ title: t('Время и часовой пояс') }} />
      <Stack.Screen name="account" options={{ title: t('Аккаунт') }} />
      <Stack.Screen name="sign-in" options={{ headerShown: false }} />
      <Stack.Screen name="reset-password" options={{ title: t('Восстановление доступа') }} />
      <Stack.Screen name="email-action" options={{ title: t('Ссылка из письма') }} />
      <Stack.Screen name="staging-access" options={{ title: t('Доступ к тестовому стенду') }} />
      <Stack.Screen name="share-probe" options={{ title: t('Входящий материал'), presentation: 'modal' }} />
      <Stack.Screen name="+not-found" options={{ title: t('Страница не найдена') }} />
    </Stack>
  </AuthProvider>;
}
