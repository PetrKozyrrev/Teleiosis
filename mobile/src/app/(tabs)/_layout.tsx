import Ionicons from '@expo/vector-icons/Ionicons';
import { Redirect, Tabs } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, fonts } from '../../theme';
import { useAuth } from '../../auth/context';
import { Loading } from '../../library/ui';
import { useTranslation } from '../../i18n';

export default function TabsLayout() {
  const t = useTranslation();
  const { state } = useAuth();
  if (state.phase === 'signedOut') return <Redirect href="/sign-in" />;
  if (state.phase === 'loading' || (state.phase === 'error' && state.busy)) {
    return <SafeAreaView style={{ flex: 1, justifyContent: 'center', backgroundColor: colors.background }}><Loading /></SafeAreaView>;
  }
  if (!state.session && (state.phase === 'error' || !state.offlineOwner)) return <Redirect href="/account" />;
  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.background }}><Tabs screenOptions={{
    headerShown: false,
    tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted,
    tabBarHideOnKeyboard: true,
    tabBarLabelStyle: { fontFamily: fonts.bold, fontSize: 11 },
    tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, paddingTop: 4 },
  }}>
    <Tabs.Screen name="index" options={{ title: t('Библиотека'), tabBarIcon: ({ focused, size }) => <Ionicons name={focused ? 'bookmark' : 'bookmark-outline'} color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="add-link" options={{ title: t('Добавить'), tabBarIcon: ({ focused, size }) => <Ionicons name="add-circle-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="progress" options={{ title: t('Прогресс'), tabBarIcon: ({ focused, size }) => <Ionicons name="bar-chart-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="settings" options={{ title: t('Профиль'), tabBarIcon: ({ focused, size }) => <Ionicons name={focused ? 'person' : 'person-outline'} color={focused ? colors.primary : colors.muted} size={size} /> }} />
  </Tabs></SafeAreaView>;
}
