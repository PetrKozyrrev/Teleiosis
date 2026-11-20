import { beforeEach, expect, jest, test } from '@jest/globals';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import { AuthApi, type IssuedSession } from '../src/auth/api';
import { AuthController } from '../src/auth/controller';
import type { Vault } from '../src/auth/vault';
import { clearAccount, listJobs } from '../src/offline/store';
import Account from '../src/app/account';

jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('../src/auth/config', () => ({ ...jest.requireActual<typeof import('../src/auth/config')>('../src/auth/config'), API_ORIGIN: 'https://example.com', STAGING_GATE: false }));
jest.mock('../src/auth/context', () => ({ useAuth: () => ({ controller: mockController, state: mockController.snapshot() }) }));
jest.mock('../src/offline/store', () => ({
  clearAccount: jest.fn(), listJobs: jest.fn(), ownerKey: (origin: string, id: number) => `${origin}/${id}`,
}));

let mockController: AuthController;
let api: AuthApi;
let storage: jest.Mocked<Vault>;
const first: IssuedSession = {
  user: { id: 1, email: 'synthetic-a@example.com', timezone: 'UTC', reminders_enabled: false, reminder_time: '09:00', email_verified_at: null },
  token: 'a'.repeat(43), token_type: 'Bearer', expires_at: '2026-12-01T00:00:00Z', absolute_expires_at: '2027-01-01T00:00:00Z',
};

beforeEach(async () => {
  storage = {
    initialize: jest.fn<Vault['initialize']>().mockResolvedValue(), load: jest.fn<Vault['load']>().mockResolvedValue(first.token),
    save: jest.fn<Vault['save']>().mockResolvedValue(), clear: jest.fn<Vault['clear']>().mockResolvedValue(),
  };
  api = new AuthApi('https://example.com', async () => null);
  jest.spyOn(api, 'current').mockResolvedValue(first);
  jest.spyOn(api, 'logout').mockResolvedValue();
  jest.spyOn(api, 'signIn').mockResolvedValue({ ...first, token: 'b'.repeat(43), user: { ...first.user, id: 2, email: 'synthetic-b@example.com' } });
  mockController = new AuthController(api, storage);
  await mockController.initialize();
  jest.mocked(listJobs).mockResolvedValue([{ id: 'synthetic-job', owner: 'https://example.com/1', state: 'pending',
    payload: '{"note":"synthetic draft"}', attempts: 0, tried_at: null, next_at: 0, reason: null, server_id: null }]);
  jest.mocked(clearAccount).mockResolvedValue();
});

test('an old logout confirmation cannot revoke the next account or delete its local data', async () => {
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  await render(<Account />);
  await fireEvent.press(screen.getByRole('button', { name: 'Выйти' }));
  await waitFor(() => expect(alert).toHaveBeenCalled());
  const confirm = alert.mock.calls[0][2]!.find(button => button.style === 'destructive')!;

  // A reset/deep link can change authentication while a native dialog survives.
  await mockController.logout(true);
  await mockController.signIn('login', 'synthetic-b@example.com', 'synthetic-password');
  jest.mocked(api.logout).mockClear();
  storage.clear.mockClear();

  await act(async () => { confirm.onPress?.(); });
  expect(api.logout).not.toHaveBeenCalled();
  expect(clearAccount).not.toHaveBeenCalled();
  expect(storage.clear).not.toHaveBeenCalled();
  expect(mockController.snapshot().session?.user.id).toBe(2);
  expect(screen.getByText('Аккаунт или сессия изменились. Повторите выход.')).toBeTruthy();
  alert.mockRestore();
});
