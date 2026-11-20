import { expect, jest, test } from '@jest/globals';
import { render } from '@testing-library/react-native';
import { Text } from 'react-native';
import { ApiError, AuthApi, type IssuedSession } from '../src/auth/api';
import { AuthController } from '../src/auth/controller';
import type { Vault } from '../src/auth/vault';
import type { Request } from '../src/library/model';
import { LibraryAccess } from '../src/library/ui';

jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('../src/auth/config', () => ({ ...jest.requireActual<typeof import('../src/auth/config')>('../src/auth/config'), API_ORIGIN: 'https://example.com' }));
jest.mock('../src/auth/context', () => ({ useAuth: () => ({ controller: mockController, state: mockController.snapshot() }) }));
jest.mock('../src/offline/store', () => ({ ownerKey: (origin: string, id: number) => `${origin}/${id}` }));
let mockController: AuthController;

test('an old screen cannot fetch the next account data using its captured request', async () => {
  const first: IssuedSession = {
    user: { id: 1, email: 'synthetic-a@example.com', timezone: 'UTC', reminders_enabled: false, reminder_time: '09:00', email_verified_at: null },
    token: 'a'.repeat(43), token_type: 'Bearer', expires_at: '2026-12-01T00:00:00Z', absolute_expires_at: '2027-01-01T00:00:00Z',
  };
  const storage: Vault = { initialize: async () => {}, load: async () => first.token, save: async () => {}, clear: async () => {} };
  const api = new AuthApi('https://example.com', async () => null);
  jest.spyOn(api, 'current').mockResolvedValue(first);
  jest.spyOn(api, 'signIn').mockResolvedValue({ ...first, token: 'b'.repeat(43), user: { ...first.user, id: 2 } });
  const transport = jest.spyOn(api, 'library').mockResolvedValue({ items: [{ id: 22, title: 'Synthetic account B only' }] });
  mockController = new AuthController(api, storage);
  await mockController.initialize();
  let captured!: Request;
  const content = (request: Request) => { captured = request; return <Text>Library fixture</Text>; };
  const view = await render(<LibraryAccess>{content}</LibraryAccess>);
  const oldRequest = captured;
  await mockController.logout(true);
  await mockController.signIn('login', 'synthetic-b@example.com', 'synthetic-password');
  await expect(oldRequest('/contents', 'GET')).rejects.toMatchObject({ status: 401 });
  expect(transport).not.toHaveBeenCalled();
  expect(mockController.snapshot().session?.user.id).toBe(2);

  await view.rerender(<LibraryAccess>{content}</LibraryAccess>);
  await expect(captured('/contents', 'GET')).resolves.toMatchObject({ items: [{ id: 22 }] });
  expect(transport).toHaveBeenCalledTimes(1);
});

test('a bound owner keeps the offline fallback status and reconnects through a fresh request', async () => {
  const first: IssuedSession = {
    user: { id: 1, email: 'synthetic-a@example.com', timezone: 'UTC', reminders_enabled: false, reminder_time: '09:00', email_verified_at: null },
    token: 'a'.repeat(43), token_type: 'Bearer', expires_at: '2026-12-01T00:00:00Z', absolute_expires_at: '2027-01-01T00:00:00Z',
  };
  const storage: Vault = { initialize: async () => {}, load: async () => first.token, lastOwner: async () => 1,
    save: async () => {}, clear: async () => {} };
  const api = new AuthApi('https://example.com', async () => null);
  jest.spyOn(api, 'current').mockRejectedValueOnce(new ApiError(0)).mockResolvedValue(first);
  const transport = jest.spyOn(api, 'library').mockResolvedValue({ items: [] });
  mockController = new AuthController(api, storage);
  await expect(mockController.initialize()).rejects.toThrow();
  let captured!: Request;
  let owner: string | null = null;
  const content = (request: Request, key: string | null) => { captured = request; owner = key; return <Text>Offline fixture</Text>; };
  const view = await render(<LibraryAccess>{content}</LibraryAccess>);
  expect(owner).toBe('https://example.com/1');
  await expect(captured('/contents', 'GET')).rejects.toMatchObject({ status: 0 });
  expect(transport).not.toHaveBeenCalled();
  await mockController.refresh();
  await view.rerender(<LibraryAccess>{content}</LibraryAccess>);
  await expect(captured('/contents', 'GET')).resolves.toMatchObject({ items: [] });
  expect(transport).toHaveBeenCalledTimes(1);
});
