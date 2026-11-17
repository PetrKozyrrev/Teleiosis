import * as SecureStore from 'expo-secure-store';
import { File, Paths } from 'expo-file-system';

const SESSION_KEY = 'teleiosis.auth.session.v1';
const GATE_KEY = 'teleiosis.auth.gateway.v1';
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainService: 'teleiosis.auth', keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

async function remove(key: string) {
  await SecureStore.deleteItemAsync(key, OPTIONS);
  if (await SecureStore.getItemAsync(key, OPTIONS) !== null) throw new Error('Не удалось очистить защищённое хранилище. Повторите на разблокированном устройстве.');
}

async function write(key: string, value: string) {
  await SecureStore.setItemAsync(key, value, OPTIONS);
  if (await SecureStore.getItemAsync(key, OPTIONS) !== value) throw new Error('Не удалось проверить запись в защищённое хранилище.');
}

export const vault = {
  async initialize() {
    if (!await SecureStore.isAvailableAsync()) throw new Error('Защищённое хранилище недоступно.');
    // OS cache does not survive uninstall/backup. Eviction conservatively logs out.
    const marker = new File(Paths.cache, 'teleiosis-installation-v1');
    if (!marker.exists) {
      await remove(SESSION_KEY);
      await remove(GATE_KEY);
      marker.create({ intermediates: true });
      marker.write('installation-v1');
      if (!marker.exists) throw new Error('Не удалось подготовить локальное хранилище.');
    }
  },
  async load(origin: string): Promise<string | null> {
    const raw = await SecureStore.getItemAsync(SESSION_KEY, OPTIONS);
    if (raw === null) return null;
    try {
      const data = JSON.parse(raw);
      if (data.version === 1 && data.origin === origin && typeof data.token === 'string' && /^[A-Za-z0-9_-]{16,128}$/.test(data.token)) return data.token;
    } catch { /* Never use malformed or differently bound credentials. */ }
    await remove(SESSION_KEY);
    return null;
  },
  async save(origin: string, token: string) { await write(SESSION_KEY, JSON.stringify({ version: 1, origin, token })); },
  async clear() { await remove(SESSION_KEY); },
  async gateway(origin: string) {
    const raw = await SecureStore.getItemAsync(GATE_KEY, OPTIONS);
    if (raw === null) return null;
    try {
      const data = JSON.parse(raw);
      if (data.origin === origin && typeof data.value === 'string' && /^Basic [A-Za-z0-9+/=]+$/.test(data.value)) return data.value as string;
    } catch { /* No credential fallback to a different server. */ }
    await remove(GATE_KEY);
    return null;
  },
  async setGateway(origin: string, password: string) {
    if (!/^[\x21-\x7e]{1,256}$/.test(password)) throw new Error('Введите пароль доступа к тестовому стенду.');
    await write(GATE_KEY, JSON.stringify({ origin, value: `Basic ${btoa(`tester:${password}`)}` }));
  },
};

export type Vault = Pick<typeof vault, 'initialize' | 'load' | 'save' | 'clear'>;
