import { Stack } from 'expo-router';
import { useFonts } from 'expo-font';
import { Inter_400Regular } from '@expo-google-fonts/inter/400Regular';
import { Inter_600SemiBold } from '@expo-google-fonts/inter/600SemiBold';
import { Inter_700Bold } from '@expo-google-fonts/inter/700Bold';
import { Manrope_700Bold } from '@expo-google-fonts/manrope/700Bold';
import { StatusBar } from 'expo-status-bar';
import { colors } from '../theme';

export default function RootLayout() {
  const [loaded, error] = useFonts({ Inter_400Regular, Inter_600SemiBold, Inter_700Bold, Manrope_700Bold });
  if (!loaded && !error) return null;
  return <>
    <StatusBar style="dark" />
    <Stack screenOptions={{ headerTintColor: colors.primary, headerStyle: { backgroundColor: colors.surface }, contentStyle: { backgroundColor: colors.background } }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="probe" options={{ title: 'Проверка устройства' }} />
      <Stack.Screen name="licenses" options={{ title: 'Лицензии шрифтов' }} />
      <Stack.Screen name="share-probe" options={{ title: 'Входящий материал', presentation: 'modal' }} />
      <Stack.Screen name="+not-found" options={{ title: 'Страница не найдена' }} />
    </Stack>
  </>;
}
