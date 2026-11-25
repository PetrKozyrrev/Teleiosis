import { fireEvent, render, screen } from '@testing-library/react-native';
import { expect, jest, test } from '@jest/globals';
import Storage from 'expo-sqlite/kv-store';
import { View } from 'react-native';
import ProfileTab from '../src/app/(tabs)/settings';
import { useAuth } from '../src/auth/context';
import type { AuthController } from '../src/auth/controller';
import { useLanguageReady, useTranslation } from '../src/i18n';
import { Notice } from '../src/library/ui';

jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: { getItem: jest.fn(), setItem: jest.fn() },
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn() },
  useFocusEffect: (callback: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
}));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));

function App() {
  const ready = useLanguageReady();
  const t = useTranslation();
  if (!ready) return null;
  return <View>
    <ProfileTab />
    <Notice>{t('Библиотека')}</Notice>
    <Notice>Не удалось выполнить запрос. Повторите позже.</Notice>
  </View>;
}

test('loads the saved language, applies a change across mounted screens and reports failed writes', async () => {
  const user = { id: 1, email: 'test@example.com', timezone: 'UTC', reminders_enabled: false,
    reminder_time: '10:00', email_verified_at: null };
  jest.mocked(useAuth).mockReturnValue({
    state: { phase: 'signedIn', busy: false, message: null, session: { user, expires_at: '', absolute_expires_at: '' } },
    controller: { captureSession: () => () => true,
      library: async () => ({ ...user, display_name: 'Все', weekly_reading_goal: 5 }),
    } as unknown as AuthController,
  });
  jest.mocked(Storage.getItem).mockResolvedValue('en');
  jest.mocked(Storage.setItem).mockRejectedValueOnce(new Error('Storage unavailable')).mockResolvedValueOnce(undefined);

  await render(<App />);
  expect(Storage.getItem).toHaveBeenCalledWith('app.language');
  expect(screen.getByText('Time and time zone')).toBeTruthy();
  expect(screen.getByText('Library')).toBeTruthy();
  expect(screen.getByText("Couldn't complete the request. Try again later.")).toBeTruthy();
  expect(screen.getByText('Все')).toBeTruthy();

  await fireEvent.press(screen.getByRole('button', { name: /App language/ }));
  expect(screen.getByRole('radio', { name: 'English', checked: true })).toBeTruthy();
  await fireEvent.press(screen.getByRole('radio', { name: 'Русский' }));
  expect(screen.getByText("Couldn't save the app language. Try again.")).toBeTruthy();
  await fireEvent.press(screen.getByRole('radio', { name: 'Русский' }));

  expect(Storage.setItem).toHaveBeenLastCalledWith('app.language', 'ru');
  expect(screen.getByText('Время и часовой пояс')).toBeTruthy();
  expect(screen.getByText('Библиотека')).toBeTruthy();
  expect(screen.getByText('Все')).toBeTruthy();
  expect(screen.queryByRole('radio', { name: 'Русский' })).toBeNull();
});
