import * as SecureStore from 'expo-secure-store';

const KEY = 'teleiosis.platform-probe.v1';
const MARKER = 'non-secret-device-probe-v1';
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainService: 'teleiosis.platform-probe',
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export type ProbeOperation = 'write' | 'read' | 'delete';

// A dedicated non-secret marker; this is deliberately separate from future auth storage.
export async function storageProbe(operation: ProbeOperation): Promise<string> {
  if (!await SecureStore.isAvailableAsync()) throw new Error('Secure storage unavailable');
  if (operation === 'write') {
    await SecureStore.setItemAsync(KEY, MARKER, OPTIONS);
    if (await SecureStore.getItemAsync(KEY, OPTIONS) !== MARKER) throw new Error('Read-back failed');
    return 'Проверочная запись сохранена и прочитана. Закройте приложение и проверьте чтение после запуска.';
  }
  if (operation === 'read') {
    const value = await SecureStore.getItemAsync(KEY, OPTIONS);
    if (value === null) return 'Проверочной записи нет.';
    if (value !== MARKER) throw new Error('Unexpected probe data');
    return 'Проверочная запись прочитана.';
  }
  await SecureStore.deleteItemAsync(KEY, OPTIONS);
  if (await SecureStore.getItemAsync(KEY, OPTIONS) !== null) throw new Error('Delete verification failed');
  return 'Проверочная запись удалена; отсутствие подтверждено чтением.';
}
