import { expect, jest, test } from '@jest/globals';
import { ApiError } from '../src/auth/api';
import { exportAccount } from '../src/account/export';
import { shareAsync } from 'expo-sharing';
import type { Request } from '../src/library/model';
const mockDelete = jest.fn();
const mockWrite = jest.fn();
jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
jest.mock('expo-file-system', () => ({
  Paths: { cache: 'cache' },
  File: class { uri = 'cache/teleiosis-export.json'; exists = true; create() {} write = mockWrite; delete = mockDelete; },
}));
jest.mock('expo-sharing', () => ({ isAvailableAsync: async () => true, shareAsync: jest.fn() }));

test('shares the server export and removes the temporary file even if the OS rejects sharing', async () => {
  jest.mocked(shareAsync).mockRejectedValueOnce(new Error('share failed'));
  const request = jest.fn<Request>().mockResolvedValue({ user: { email: 'synthetic@example.com' }, contents: [] });
  await expect(exportAccount(request)).rejects.toThrow('share failed');
  expect(request).toHaveBeenCalledWith('/me/export', 'GET');
  expect(mockWrite).toHaveBeenCalledWith(expect.stringContaining('synthetic@example.com'));
  expect(mockDelete).toHaveBeenCalledTimes(1);
});

test('does not export data after switching accounts', async () => {
  const request = jest.fn<Request>();
  await expect(exportAccount(request, () => false)).rejects.toThrow('Аккаунт изменился');
  expect(request).not.toHaveBeenCalled();
});

test('identifies a gateway rejection before writing an export file', async () => {
  mockWrite.mockClear();
  const request = jest.fn<Request>().mockRejectedValue(new ApiError(401, true));
  await expect(exportAccount(request)).rejects.toThrow('Выгрузка недоступна через шлюз стенда');
  expect(mockWrite).not.toHaveBeenCalled();
});
