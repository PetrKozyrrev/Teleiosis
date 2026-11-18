import { beforeEach, expect, jest, test } from '@jest/globals';
import { ApiError, AuthApi, type IssuedSession } from '../src/auth/api';
import { AuthController } from '../src/auth/controller';
import type { Vault } from '../src/auth/vault';

jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
const issued: IssuedSession = { user: { id: 1, email: 'user@example.com', timezone: 'UTC', reminders_enabled: true, reminder_time: '10:00', email_verified_at: null }, token: 'a'.repeat(43), token_type: 'Bearer', expires_at: '2026-12-01T00:00:00Z', absolute_expires_at: '2027-01-01T00:00:00Z' };
let storage: jest.Mocked<Vault>;
let api: AuthApi;
let controller: AuthController;

beforeEach(() => {
  storage = { initialize: jest.fn<() => Promise<void>>().mockResolvedValue(), load: jest.fn<Vault['load']>().mockResolvedValue(issued.token), save: jest.fn<Vault['save']>().mockResolvedValue(), clear: jest.fn<() => Promise<void>>().mockResolvedValue() };
  api = new AuthApi('https://example.com', async () => null);
  jest.spyOn(api, 'signIn').mockResolvedValue(issued);
  jest.spyOn(api, 'current').mockResolvedValue(issued);
  jest.spyOn(api, 'logout').mockResolvedValue();
  jest.spyOn(api, 'request').mockResolvedValue(undefined);
  controller = new AuthController(api, storage);
});

test('restores only after checking server and never exposes token in React state', async () => {
  const { token: _token, token_type: _type, ...session } = issued;
  jest.mocked(api.current).mockResolvedValue(session);
  await controller.initialize();
  expect(controller.snapshot().phase).toBe('signedIn');
  expect(JSON.stringify(controller.snapshot())).not.toContain(issued.token);
});

test('removes definitively expired sessions', async () => {
  jest.mocked(api.current).mockRejectedValue(new ApiError(401));
  await controller.initialize();
  expect(storage.clear).toHaveBeenCalledTimes(1);
  expect(controller.snapshot().phase).toBe('signedOut');
});

test.each([new ApiError(0), new ApiError(503), new ApiError(401, true)])('retains credentials during offline, 5xx or gateway failure', async error => {
  jest.mocked(api.current).mockRejectedValue(error);
  await expect(controller.initialize()).rejects.toThrow();
  expect(storage.clear).not.toHaveBeenCalled();
  expect(controller.snapshot().phase).toBe('offline');
});

test('cannot sign in until token is safely persisted; failed save revokes new token', async () => {
  storage.load.mockResolvedValue(null);
  await controller.initialize();
  storage.save.mockRejectedValue(new Error('private native internals'));
  await expect(controller.signIn('login', 'user@example.com', 'password')).rejects.not.toThrow('private native internals');
  expect(api.logout).toHaveBeenCalledWith(issued.token);
  expect(controller.snapshot().phase).toBe('signedOut');
  expect(JSON.stringify(controller.snapshot())).not.toContain(issued.token);
});

test('prevents overlapping auth mutations and duplicate login requests', async () => {
  storage.load.mockResolvedValue(null);
  await controller.initialize();
  let resolve!: (value: IssuedSession) => void;
  jest.mocked(api.signIn).mockReturnValue(new Promise(done => { resolve = done; }));
  const first = controller.signIn('login', 'user@example.com', 'password');
  await expect(controller.signIn('login', 'user@example.com', 'password')).rejects.toThrow('Дождитесь');
  expect(api.signIn).toHaveBeenCalledTimes(1);
  resolve(issued); await first;
  expect(JSON.stringify(controller.snapshot())).not.toContain(issued.token);
});

test('failed remote logout retains session until explicit local-only logout', async () => {
  await controller.initialize();
  jest.mocked(api.logout).mockRejectedValue(new ApiError(0));
  await expect(controller.logout()).rejects.toThrow();
  expect(storage.clear).not.toHaveBeenCalled();
  expect(controller.snapshot().phase).toBe('signedIn');
  await controller.logout(true);
  expect(storage.clear).toHaveBeenCalledTimes(1);
  expect(controller.snapshot().phase).toBe('signedOut');
});

test('does not report successful deletion when secure storage deletion fails', async () => {
  await controller.initialize();
  storage.clear.mockRejectedValue(new Error('native failure'));
  await expect(controller.logout()).rejects.toThrow();
  expect(controller.snapshot().phase).toBe('error');
  expect(controller.snapshot().session).toBeNull();
});

test('a definite API 401 with a failed local wipe cannot leave authenticated UI state', async () => {
  await controller.initialize();
  jest.mocked(api.current).mockRejectedValue(new ApiError(401));
  storage.clear.mockRejectedValue(new Error('native failure'));
  await expect(controller.refresh()).rejects.toThrow();
  expect(controller.snapshot().phase).toBe('error');
  expect(controller.snapshot().session).toBeNull();
});

test('verification success remains success if subsequent profile refresh fails', async () => {
  await controller.initialize();
  jest.mocked(api.current).mockRejectedValue(new ApiError(0));
  await expect(controller.confirm('verify', 'b'.repeat(43))).resolves.toContain('Адрес подтверждён');
});

test('reset success reports local cleanup failure without repeating the one-time operation', async () => {
  await controller.initialize();
  storage.clear.mockRejectedValue(new Error('native failure'));
  await expect(controller.confirm('reset', 'b'.repeat(43), 'new password')).resolves.toContain('Пароль изменён');
  expect(api.request).toHaveBeenCalledTimes(1);
  expect(controller.snapshot().phase).toBe('error');
});

test('library loses the session only for the API 401 and never retries a write', async () => {
  await controller.initialize();
  const library = jest.spyOn(api, 'library').mockRejectedValueOnce(new ApiError(401, true))
    .mockRejectedValueOnce(new ApiError(0)).mockRejectedValueOnce(new ApiError(401));
  await expect(controller.library('/contents', 'GET')).rejects.toMatchObject({ gateway: true });
  await expect(controller.library('/contents', 'POST', { note: 'draft' })).rejects.toMatchObject({ status: 0 });
  expect(controller.snapshot().phase).toBe('signedIn');
  expect(storage.clear).not.toHaveBeenCalled();
  await expect(controller.library('/contents', 'GET')).rejects.toMatchObject({ status: 401, gateway: false });
  expect(library.mock.calls).toEqual([
    ['/contents', 'GET', issued.token, undefined],
    ['/contents', 'POST', issued.token, { note: 'draft' }],
    ['/contents', 'GET', issued.token, undefined],
  ]);
  expect(storage.clear).toHaveBeenCalledTimes(1);
  expect(controller.snapshot()).toMatchObject({ phase: 'signedOut', session: null });
});

test('drops a library response from a session that signed out while it was loading', async () => {
  await controller.initialize();
  let resolve!: (value: unknown) => void;
  jest.spyOn(api, 'library').mockReturnValue(new Promise(done => { resolve = done; }));
  const pending = controller.library('/contents', 'GET');
  await controller.logout();
  resolve({ items: [{ id: 12 }] });
  await expect(pending).rejects.toMatchObject({ status: 401 });
});

test('allows only the bound offline owner after a cold network failure', async () => {
  storage.lastOwner = jest.fn<NonNullable<Vault['lastOwner']>>().mockResolvedValue(issued.user.id);
  jest.mocked(api.current).mockRejectedValue(new ApiError(0));
  await expect(controller.initialize()).rejects.toThrow();
  expect(controller.snapshot()).toMatchObject({ phase: 'offline', session: null, offlineOwner: issued.user.id });
  await expect(controller.library('/contents', 'GET')).rejects.toMatchObject({ status: 0 });

  jest.mocked(api.current).mockResolvedValue(issued);
  await controller.refresh();
  const send = jest.spyOn(api, 'library');
  await expect(controller.library('/contents/submissions', 'POST', { note: 'old account' }, {
    ownerId: issued.user.id + 1, idempotencyKey: 'another-owner',
  })).rejects.toMatchObject({ status: 401 });
  expect(send).not.toHaveBeenCalled();
});
