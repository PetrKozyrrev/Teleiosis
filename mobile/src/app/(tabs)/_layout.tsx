import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, fonts } from '../../theme';

export default function TabsLayout() {
  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.background }}><Tabs screenOptions={{
    headerShown: false,
    tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted,
    tabBarHideOnKeyboard: true,
    tabBarLabelStyle: { fontFamily: fonts.bold, fontSize: 11 },
    tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, paddingTop: 4 },
  }}>
    <Tabs.Screen name="index" options={{ title: 'Библиотека', tabBarIcon: ({ focused, size }) => <Ionicons name={focused ? 'bookmark' : 'bookmark-outline'} color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="add-link" options={{ title: 'Добавить', tabBarIcon: ({ focused, size }) => <Ionicons name="add-circle-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="progress" options={{ title: 'Прогресс', tabBarIcon: ({ focused, size }) => <Ionicons name="bar-chart-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="settings" options={{ title: 'Профиль', tabBarIcon: ({ focused, size }) => <Ionicons name={focused ? 'person' : 'person-outline'} color={focused ? colors.primary : colors.muted} size={size} /> }} />
  </Tabs></SafeAreaView>;
}
