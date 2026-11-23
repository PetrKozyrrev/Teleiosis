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

export default function RootLayout() {
  useEffect(clearPdfPreviews, []);
  const [loaded, error] = useFonts({ Inter_400Regular, Inter_600SemiBold, Inter_700Bold });
  if (!loaded && !error) return null;
  return <AuthProvider>
    <OfflineSync />
    <StatusBar style="dark" />
    <Stack screenOptions={{ headerTintColor: colors.primary, headerStyle: { backgroundColor: colors.surface }, contentStyle: { backgroundColor: colors.background } }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="library/[id]" options={{ title: 'Материал' }} />
      <Stack.Screen name="library/organization" options={{ title: 'Теги и коллекции' }} />
      <Stack.Screen name="library/organize" options={{ title: 'Теги и коллекции материала' }} />
      <Stack.Screen name="library/categories" options={{ title: 'Категории' }} />
      <Stack.Screen name="library/import" options={{ title: 'Импорт библиотеки' }} />
      <Stack.Screen name="library/pdf" options={{ title: 'PDF' }} />
      <Stack.Screen name="review" options={{ title: 'Повторение' }} />
      <Stack.Screen name="plan" options={{ title: 'Недельный план' }} />
      <Stack.Screen name="queue" options={{ title: 'Очередь и входящие' }} />
      <Stack.Screen name="probe" options={{ title: 'Проверка устройства' }} />
      <Stack.Screen name="licenses" options={{ title: 'Лицензии шрифтов' }} />
      <Stack.Screen name="preferences" options={{ title: 'Настройки аккаунта' }} />
      <Stack.Screen name="account" options={{ title: 'Аккаунт' }} />
      <Stack.Screen name="sign-in" options={{ title: '', headerStyle: { backgroundColor: colors.background }, headerShadowVisible: false }} />
      <Stack.Screen name="reset-password" options={{ title: 'Восстановление доступа' }} />
      <Stack.Screen name="email-action" options={{ title: 'Ссылка из письма' }} />
      <Stack.Screen name="staging-access" options={{ title: 'Доступ к тестовому стенду' }} />
      <Stack.Screen name="share-probe" options={{ title: 'Входящий материал', presentation: 'modal' }} />
      <Stack.Screen name="+not-found" options={{ title: 'Страница не найдена' }} />
    </Stack>
  </AuthProvider>;
}
