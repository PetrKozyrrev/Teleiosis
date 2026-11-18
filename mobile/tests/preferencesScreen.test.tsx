import { beforeEach, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';
import Preferences from '../src/app/preferences';
import { useAuth } from '../src/auth/context';
import type { AuthController } from '../src/auth/controller';
import type { Request } from '../src/library/model';

jest.mock('../src/offline/store', () => ({ ownerKey: () => 'account' }));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('../src/library/ui', () => {
  const original = jest.requireActual<typeof import('../src/library/ui')>('../src/library/ui');
  return { ...original, LibraryAccess: ({ children }: { children: (request: Request, owner: string) => unknown }) => children(mockRequest, 'account') };
});
jest.mock('../src/account/export', () => ({ exportAccount: jest.fn() }));
jest.mock('../src/account/cleanup', () => ({ clearDeletedData: jest.fn() }));
jest.mock('expo-router', () => ({ router: { replace: jest.fn() } }));
const mockRequest = jest.fn<Request>();
const refresh = jest.fn<() => Promise<void>>();
beforeEach(() => {
  mockRequest.mockReset().mockImplementation(async path => {
    if (path.startsWith('/contents?')) return { items: [{ id: 12, title: 'Тестовый материал' }], total: 1, limit: 20, offset: 0 };
    if (path === '/contents/12/reminder') return null;
    return { id: 1, email: 'synthetic@example.com', timezone: 'UTC', reminders_enabled: true, reminder_time: '09:00' };
  });
  refresh.mockResolvedValue(undefined);
  jest.mocked(useAuth).mockReturnValue({
    controller: { refresh } as unknown as AuthController,
    state: { phase: 'signedIn', busy: false, session: null, message: null },
  });
});
test('saves the selected IANA timezone and time using the shared API', async () => {
  await render(<Preferences />);
  await fireEvent.changeText(screen.getByLabelText('Часовой пояс IANA'), 'Europe/Moscow');
  await fireEvent.changeText(screen.getByLabelText('Время ежедневной подборки (ЧЧ:ММ)'), '10:30');
  await fireEvent.press(screen.getByRole('button', { name: 'Сохранить настройки' }));
  expect(mockRequest).toHaveBeenCalledWith('/me/settings', 'PATCH', { timezone: 'Europe/Moscow', reminder_time: '10:30', reminders_enabled: true });
  expect(screen.getByText('Настройки сохранены.')).toBeTruthy();
});

test('manages a selected material reminder from account settings', async () => {
  await render(<Preferences />);
  await fireEvent.press(screen.getByRole('button', { name: 'Напоминания по материалам' }));
  const choose = await screen.findByRole('button', { name: 'Материал для напоминания · Выберите материал' });
  await fireEvent.press(choose);
  await fireEvent.press(screen.getByRole('radio', { name: 'Тестовый материал' }));
  expect(await screen.findByLabelText('Дата и время напоминания')).toBeTruthy();
  expect(mockRequest).toHaveBeenCalledWith('/contents/12/reminder', 'GET');
});
