import { beforeEach, expect, jest, test } from '@jest/globals';
import * as SecureStore from 'expo-secure-store';
import { vault } from '../src/auth/vault';

const mockData = new Map<string, string>();
let mockMarkerExists = true;
jest.mock('expo-secure-store', () => ({ isAvailableAsync: jest.fn(), setItemAsync: jest.fn(), getItemAsync: jest.fn(), deleteItemAsync: jest.fn(), WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6 }));
jest.mock('expo-file-system', () => ({
  Paths: { cache: 'file://test-cache/' },
  File: class {
    get exists() { return mockMarkerExists; }
    create() { mockMarkerExists = true; }
    write() {}
  },
}));
const origin = 'https://example.com';
const token = 'a'.repeat(43);
const key = 'teleiosis.auth.session.v1';

beforeEach(() => {
  mockData.clear(); mockMarkerExists = true;
  jest.mocked(SecureStore.isAvailableAsync).mockResolvedValue(true);
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async key => mockData.get(key) ?? null);
  jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => { mockData.set(key, value); });
  jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async key => { mockData.delete(key); });
});

test('clears old keychain credentials when the OS installation/cache marker is absent', async () => {
  mockMarkerExists = false;
  mockData.set(key, 'old-keychain-data');
  mockData.set('teleiosis.auth.gateway.v1', 'old-gateway-data');
  await vault.initialize();
  expect(mockData.size).toBe(0);
  expect(mockMarkerExists).toBe(true);
});
test('retains credentials on ordinary restart and validates save/read-back', async () => {
  await vault.initialize();
  await vault.save(origin, token);
  await vault.initialize();
  expect(await vault.load(origin)).toBe(token);
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith(key, expect.any(String), { keychainService: 'teleiosis.auth', keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
});
test.each(['invalid-json', JSON.stringify({ version: 1, origin: 'https://different.example', token }), JSON.stringify({ version: 1, origin, token: 'invalid token' })])('does not reuse malformed or differently bound credentials', async raw => {
  mockData.set(key, raw);
  expect(await vault.load(origin)).toBeNull();
  expect(mockData.has(key)).toBe(false);
});
test('does not accept partial writes or successful-looking failed deletion', async () => {
  jest.mocked(SecureStore.setItemAsync).mockResolvedValue(undefined);
  await expect(vault.save(origin, token)).rejects.toThrow();
  mockData.set(key, 'data');
  jest.mocked(SecureStore.deleteItemAsync).mockResolvedValue(undefined);
  await expect(vault.clear()).rejects.toThrow();
});
test('binds the staging credential to its own origin as well', async () => {
  await vault.setGateway(origin, 'synthetic-gateway-only', async () => {});
  expect(await vault.gateway(origin)).toMatch(/^Basic /);
  expect(await vault.gateway('https://different.example')).toBeNull();
});

test('trims a pasted password and preserves the saved gateway on rejection', async () => {
  const verify = jest.fn<(value: string) => Promise<void>>().mockResolvedValue(undefined);
  await vault.setGateway(origin, '  synthetic-gateway-only\n', verify);
  expect(verify).toHaveBeenCalledWith('Basic dGVzdGVyOnN5bnRoZXRpYy1nYXRld2F5LW9ubHk=');
  const saved = await vault.gateway(origin);
  verify.mockRejectedValue(new Error('Gateway rejected'));
  await expect(vault.setGateway(origin, 'incorrect', verify)).rejects.toThrow('Gateway rejected');
  expect(await vault.gateway(origin)).toBe(saved);
});
