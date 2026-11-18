import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import { colors } from '../../theme';

export default function TabsLayout() {
  return <Tabs screenOptions={{
    headerTitle: 'Телеосис',
    headerStyle: { backgroundColor: colors.surface }, headerTintColor: colors.text,
    tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted,
    tabBarStyle: { backgroundColor: colors.surface },
  }}>
    <Tabs.Screen name="index" options={{ title: 'Библиотека', tabBarIcon: ({ focused, size }) => <Ionicons name="library-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="progress" options={{ title: 'Прогресс', tabBarIcon: ({ focused, size }) => <Ionicons name="bar-chart-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="settings" options={{ title: 'Настройки', tabBarIcon: ({ focused, size }) => <Ionicons name="settings-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
  </Tabs>;
}
