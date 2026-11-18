/// <reference types="node" />
import { afterEach, beforeEach, expect, jest, test } from '@jest/globals';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync as MockDatabaseSync, type SQLInputValue } from 'node:sqlite';

jest.mock('expo-crypto', () => ({ randomUUID: jest.requireActual<typeof import('node:crypto')>('node:crypto').randomUUID }));
jest.mock('expo-sqlite', () => ({
  openDatabaseAsync: async () => {
    mockDb = new MockDatabaseSync(mockFilename);
    const connection = mockDb;
    const adapter = {
      execAsync: async (sql: string) => connection.exec(sql),
      runAsync: async (sql: string, ...args: SQLInputValue[]) => connection.prepare(sql).run(...args),
      getFirstAsync: async (sql: string, ...args: SQLInputValue[]) => connection.prepare(sql).get(...args) ?? null,
      getAllAsync: async (sql: string, ...args: SQLInputValue[]) => connection.prepare(sql).all(...args),
      withExclusiveTransactionAsync: async (operation: (transaction: unknown) => Promise<void>) => {
        connection.exec('BEGIN');
        try { await operation(adapter); connection.exec('COMMIT'); }
        catch (error) { connection.exec('ROLLBACK'); throw error; }
      },
    };
    return adapter;
  },
}));
jest.mock('../src/offline/native', () => ({}));
jest.mock('react-native', () => ({ Platform: { OS: 'android' } }));

let mockDb: MockDatabaseSync;
let mockFilename: string;
let directory: string;
const owner = 'https://example.com/1';
const other = 'https://example.com/2';

function loadModules() {
  const store = jest.requireActual<typeof import('../src/offline/store')>('../src/offline/store');
  const cache = jest.requireActual<typeof import('../src/offline/cache')>('../src/offline/cache');
  const dispatch = jest.requireActual<typeof import('../src/offline/dispatch')>('../src/offline/dispatch');
  const api = jest.requireActual<typeof import('../src/auth/api')>('../src/auth/api');
  return { store, cache, dispatch, api };
}

beforeEach(() => {
  jest.resetModules();
  directory = mkdtempSync(join(tmpdir(), 'teleiosis-sqlite-'));
  mockFilename = join(directory, 'test.db');
});
afterEach(() => {
  mockDb?.close();
  rmSync(directory, { recursive: true, force: true });
});

test('replays an interrupted request with the same owner, immutable payload and UUID after restart', async () => {
  let modules = loadModules();
  const { store } = modules;
  await store.importDraft({ note: 'Проверочная заметка' }, 'a3adc2ca-b49c-4c7e-9b38-003189ffddf9');
  expect(await store.listJobs(owner)).toHaveLength(0);
  const [inbox] = await store.listJobs(store.unassigned);
  await store.assignDraft(inbox.id, owner);
  const sent = (await store.claim(owner, 1_000))!;
  expect(await store.claim(other, 1_000)).toBeNull();
  await expect(store.enqueue(owner, { note: 'Устаревшее редактирование' }, sent.id)).rejects.toThrow();

  const receipts = new Map<string, { id: number }>();
  let loseReply = true;
  const server: import('../src/library/model').Request = async (path, method, body, options) => {
    expect(path).toBe('/contents/submissions');
    expect(method).toBe('POST');
    expect(body).toEqual({ note: 'Проверочная заметка' });
    expect(options).toEqual({ ownerId: 1, idempotencyKey: sent.id });
    const id = options!.idempotencyKey!;
    if (!receipts.has(id)) receipts.set(id, { id: 5 });
    if (loseReply) { loseReply = false; throw new modules.api.ApiError(0); }
    return receipts.get(id);
  };
  expect((await modules.dispatch.dispatch(sent, 1, server, 1_000)).state).toBe('retry_wait');

  // A process can stop after the server commits but before it saves the retry result.
  mockDb.close();
  jest.resetModules();
  modules = loadModules();
  const replay = (await modules.store.claim(owner, 1_100))!;
  expect(replay.id).toBe(sent.id);
  expect(replay.payload).toBe(sent.payload);
  expect(replay.attempts).toBe(2);
  const outcome = await modules.dispatch.dispatch(replay, 1, server, 1_100);
  expect(outcome).toMatchObject({ state: 'synced', serverId: 5 });
  await modules.store.settle(replay, outcome.state, outcome.reason, outcome.nextAt, outcome.serverId, outcome.material);
  expect(receipts.size).toBe(1);
  expect(await modules.cache.cachedMaterial(owner, 5)).toMatchObject({ value: { id: 5 } });
  expect(await modules.cache.cachedMaterial(other, 5)).toBeNull();
  await modules.store.importDraft({ note: 'Redelivered' }, inbox.id);
  expect(await modules.store.listJobs(modules.store.unassigned)).toHaveLength(0);
});

test('scopes cached search and protects pending drafts at logout', async () => {
  const { store, cache } = loadModules();
  const { initialFilters } = jest.requireActual<typeof import('../src/library/model')>('../src/library/model');
  await store.enqueue(owner, { note: 'Частная заметка' });
  await cache.remember(owner, '/contents?limit=20', { items: [{ id: 1, title: 'Загруженная карточка' }] });
  expect(await cache.cachedList(owner, { ...initialFilters, q: 'карточка' }, 0)).toMatchObject({ value: { total: 1 } });
  expect(await cache.cachedList(owner, { ...initialFilters, q: 'незагруженная' }, 0)).toMatchObject({ value: { total: 0 } });
  expect(await cache.cachedList(other, initialFilters, 0)).toBeNull();
  await expect(store.clearAccount(owner, false)).rejects.toThrow();
  expect(await store.listJobs(owner)).toHaveLength(1);
  await store.clearAccount(owner, true);
  expect(await store.listJobs(owner)).toHaveLength(0);
  expect(await cache.cachedList(owner, initialFilters, 0)).toBeNull();
});

test('respects server backoff and keeps expired uncertain requests for the user', async () => {
  const { store, dispatch, api } = loadModules();
  await store.enqueue(owner, { note: 'Retry' });
  const job = (await store.claim(owner, 1_000))!;
  const response = (status: number, delay?: number, existingId?: number) => async () => {
    throw new api.ApiError(status, false, delay, existingId);
  };
  const outcomes = [
    [response(429, 60), { state: 'retry_wait', reason: 'rate', nextAt: 61_000 }],
    [response(401), { state: 'needs_auth' }],
    [response(409, undefined, 9), { state: 'needs_action', reason: 'duplicate', serverId: 9 }],
    [response(409), { state: 'needs_action', reason: 'conflict' }],
    [response(422), { state: 'needs_action', reason: 'invalid' }],
    [response(503), { state: 'retry_wait', reason: 'network' }],
    [response(410), { state: 'needs_action', reason: 'deleted' }],
  ] as const;
  for (const [send, expected] of outcomes) {
    expect(await dispatch.dispatch(job, 1, send, 1_000, () => 0.5)).toMatchObject(expected);
  }
  const neverSend = jest.fn<import('../src/library/model').Request>();
  expect(await dispatch.dispatch(job, 1, neverSend, 1_000 + dispatch.maxRetryAge)).toEqual({ state: 'needs_action', reason: 'expired' });
  expect(neverSend).not.toHaveBeenCalled();

  await store.settle(job, 'retry_wait', 'rate', 61_000);
  await store.retry(owner, job.id);
  expect(await store.claim(owner, 60_999)).toBeNull();
  expect(await store.claim(owner, 61_000)).toMatchObject({ id: job.id, attempts: 2 });
});
