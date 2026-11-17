import { beforeEach, expect, jest, test } from '@jest/globals';
import * as SecureStore from 'expo-secure-store';
import { storageProbe } from '../src/platform/storageProbe';

jest.mock('expo-secure-store', () => ({
  isAvailableAsync: jest.fn(), setItemAsync: jest.fn(), getItemAsync: jest.fn(), deleteItemAsync: jest.fn(),
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
}));

beforeEach(() => {
  jest.mocked(SecureStore.isAvailableAsync).mockResolvedValue(true);
});

test('does not use storage if the platform does not support it', async () => {
  jest.mocked(SecureStore.isAvailableAsync).mockResolvedValue(false);
  await expect(storageProbe('write')).rejects.toThrow();
  expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
});

test('validates read-back and uses a separate device-only keychain service', async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue('non-secret-device-probe-v1');
  await expect(storageProbe('write')).resolves.toContain('сохранена и прочитана');
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith('teleiosis.platform-probe.v1', expect.any(String), {
    keychainService: 'teleiosis.platform-probe', keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  await expect(storageProbe('write')).rejects.toThrow('Read-back failed');
});

test('reports missing marker and does not reveal unexpected stored contents', async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  await expect(storageProbe('read')).resolves.toContain('нет');
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue('private-stored-value');
  await expect(storageProbe('read')).rejects.toThrow('Unexpected probe data');
});

test('verifies deletion rather than promising success on a failed delete', async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  await expect(storageProbe('delete')).resolves.toContain('отсутствие подтверждено');
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue('still-present');
  await expect(storageProbe('delete')).rejects.toThrow('Delete verification failed');
});
