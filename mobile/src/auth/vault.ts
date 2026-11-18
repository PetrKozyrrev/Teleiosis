import * as SecureStore from 'expo-secure-store';
import { File, Paths } from 'expo-file-system';

const SESSION_KEY = 'teleiosis.auth.session.v1';
const GATE_KEY = 'teleiosis.auth.gateway.v1';
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainService: 'teleiosis.auth', keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

const BASE64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function stagingAuthorization(password: string): string {
  const value = password.trim();
  if (!/^[\x21-\x7e]{1,256}$/.test(value)) throw new Error('Введите только пароль доступа к стенду.');
  // The gateway issues ASCII passwords. Encode without a browser global.
  const credentials = `tester:${value}`;
  let encoded = '';
  for (let i = 0; i < credentials.length; i += 3) {
    const first = credentials.charCodeAt(i);
    const second = credentials.charCodeAt(i + 1) || 0;
    const third = credentials.charCodeAt(i + 2) || 0;
    encoded += BASE64[first >> 2] + BASE64[((first & 3) << 4) | (second >> 4)];
    encoded += i + 1 < credentials.length ? BASE64[((second & 15) << 2) | (third >> 6)] : '=';
    encoded += i + 2 < credentials.length ? BASE64[third & 63] : '=';
  }
  return `Basic ${encoded}`;
}

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
  async save(origin: string, token: string, ownerId?: number) {
    await write(SESSION_KEY, JSON.stringify({ version: 1, origin, token, ownerId }));
  },
  async lastOwner(origin: string, token: string): Promise<number | null> {
    const raw = await SecureStore.getItemAsync(SESSION_KEY, OPTIONS);
    if (!raw) return null;
    try {
      const data = JSON.parse(raw);
      return data.version === 1 && data.origin === origin && data.token === token &&
        Number.isSafeInteger(data.ownerId) && data.ownerId > 0 ? data.ownerId : null;
    } catch { return null; }
  },
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
  async setGateway(origin: string, password: string, verify: (authorization: string) => Promise<void>) {
    const value = stagingAuthorization(password);
    await verify(value);
    await write(GATE_KEY, JSON.stringify({ origin, value }));
  },
};

export type Vault = Pick<typeof vault, 'initialize' | 'load' | 'save' | 'clear'> &
  Partial<Pick<typeof vault, 'lastOwner'>>;
