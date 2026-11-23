import { randomUUID } from 'expo-crypto';
import { openDatabaseAsync, type SQLiteDatabase } from 'expo-sqlite';
import { Platform } from 'react-native';
import { nativeStorage } from './native';

export type Draft = { url?: string; note?: string; title?: string; category_id?: number | null; collection_ids?: number[] };
export type JobState = 'draft' | 'pending' | 'sending' | 'retry_wait' | 'needs_auth' | 'needs_action' | 'synced';
export type Job = {
  id: string; owner: string; payload: string; state: JobState; attempts: number;
  tried_at: number | null; next_at: number; reason: string | null; server_id: number | null;
};
export const unassigned = '';
export const ownerKey = (origin: string, userId: number) => `${origin}/${userId}`;

let connection: Promise<SQLiteDatabase> | undefined;
const listeners = new Set<(synced: boolean) => void>();
const ownerGenerations = new Map<string, number>();
export const generation = (owner: string) => ownerGenerations.get(owner) ?? 0;
export function subscribe(listener: (synced: boolean) => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
function changed(synced = false) {
  listeners.forEach(listener => listener(synced));
}

async function open() {
  const directory = Platform.OS === 'ios' ? await nativeStorage().databaseDirectory() : undefined;
  const db = await openDatabaseAsync('teleiosis.db', {}, directory);
  await db.execAsync(`
    PRAGMA journal_mode = WAL;
    PRAGMA secure_delete = ON;
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL, payload TEXT NOT NULL,
      state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, tried_at INTEGER,
      next_at INTEGER NOT NULL DEFAULT 0, reason TEXT, server_id INTEGER, created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS queue_owner ON jobs(owner, state, next_at);
    CREATE TABLE IF NOT EXISTS snapshots (
      owner TEXT NOT NULL, path TEXT NOT NULL, payload TEXT NOT NULL, updated_at INTEGER NOT NULL,
      PRIMARY KEY(owner, path)
    );
    CREATE TABLE IF NOT EXISTS imported_shares (id TEXT PRIMARY KEY NOT NULL);
    UPDATE jobs SET state = 'pending' WHERE state = 'sending';
  `);
  return db;
}
export function database() {
  connection ??= open().catch(error => { connection = undefined; throw error; });
  return connection;
}

let writes = Promise.resolve();
export function mutate<T>(operation: (db: SQLiteDatabase) => Promise<T>): Promise<T> {
  const task = writes.then(async () => operation(await database()));
  writes = task.then(() => {}, () => {});
  return task;
}

export async function listJobs(owner: string) {
  return (await database()).getAllAsync<Job>('SELECT * FROM jobs WHERE owner = ? ORDER BY created_at DESC, id', owner);
}

export async function getJob(owner: string, id: string) {
  return (await database()).getFirstAsync<Job>('SELECT * FROM jobs WHERE owner = ? AND id = ?', owner, id);
}

export async function enqueue(owner: string, payload: Draft, edit?: string) {
  await mutate(async db => {
    const id = randomUUID();
    const serialized = JSON.stringify(payload);
    if (edit) {
      const result = await db.runAsync(`
        UPDATE jobs SET id = CASE WHEN attempts = 0 THEN id ELSE ? END, payload = ?,
          state = ?, attempts = 0, tried_at = NULL, next_at = 0, reason = NULL
        WHERE owner = ? AND id = ? AND (
          (state IN ('draft', 'pending') AND attempts = 0) OR
          (state = 'needs_action' AND reason IN ('invalid', 'category', 'collection'))
        )
      `, id, serialized, owner ? 'pending' : 'draft', owner, edit);
      if (!result.changes) throw new Error('Этот черновик уже отправляется. Проверьте очередь.');
    } else {
      await db.runAsync('INSERT INTO jobs(id,owner,payload,state,created_at) VALUES(?,?,?,?,?)',
        id, owner, serialized, owner ? 'pending' : 'draft', Date.now());
    }
  });
  changed();
}

export async function importDraft(payload: Draft, sourceId?: string) {
  await mutate(async db => {
    const json = JSON.stringify(payload);
    const id = sourceId ?? randomUUID();
    // A re-delivered Android intent can arrive before its native payload was cleared.
    if (sourceId) {
      await db.withExclusiveTransactionAsync(async transaction => {
        const receipt = await transaction.runAsync('INSERT OR IGNORE INTO imported_shares(id) VALUES(?)', id);
        if (receipt.changes) await transaction.runAsync(
          'INSERT INTO jobs(id,owner,payload,state,created_at) VALUES(?,?,?,?,?)',
          id, unassigned, json, 'draft', Date.now());
      });
    } else {
      await db.runAsync(`INSERT INTO jobs(id,owner,payload,state,created_at)
        SELECT ?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM jobs WHERE owner = ? AND payload = ?)`,
      id, unassigned, json, 'draft', Date.now(), unassigned, json);
    }
  });
  changed();
}

export async function assignDraft(id: string, owner: string) {
  if (!owner) throw new Error('Войдите, чтобы добавить входящий материал.');
  const result = await mutate(db => db.runAsync(
    "UPDATE jobs SET owner = ?, state = 'pending' WHERE id = ? AND owner = ? AND state = 'draft'",
    owner, id, unassigned));
  if (!result.changes) throw new Error('Входящий черновик уже обработан.');
  changed();
}

export async function claim(owner: string, now: number) {
  const job = await mutate(db => db.getFirstAsync<Job>(`
    UPDATE jobs SET state = 'sending', attempts = attempts + 1, tried_at = COALESCE(tried_at, ?)
    WHERE id = (SELECT candidate.id FROM jobs AS candidate WHERE candidate.owner = ?
      AND candidate.state IN ('pending','sending','retry_wait','needs_auth') AND candidate.next_at <= ?
      AND NOT EXISTS (SELECT 1 FROM jobs AS limited WHERE limited.owner = candidate.owner
        AND limited.state = 'retry_wait' AND limited.reason = 'rate' AND limited.next_at > ?)
      ORDER BY candidate.created_at, candidate.id LIMIT 1)
    RETURNING *
  `, now, owner, now, now));
  if (job) changed();
  return job;
}

export async function settle(job: Job, state: JobState, reason: string | null = null, nextAt = 0,
  serverId: number | null = null, material?: object) {
  await mutate(db => db.withExclusiveTransactionAsync(async transaction => {
    const result = await transaction.runAsync(`
      UPDATE jobs SET state = ?, reason = ?, next_at = ?, server_id = ?,
        payload = CASE WHEN ? = 'synced' THEN '{}' ELSE payload END
      WHERE owner = ? AND id = ? AND state = 'sending'
    `, state, reason, nextAt, serverId, state, job.owner, job.id);
    if (result.changes && material && serverId !== null) {
      await saveSnapshot(transaction, job.owner, `/contents/${serverId}`, material);
      await transaction.runAsync(`
        DELETE FROM jobs WHERE id IN (SELECT id FROM jobs WHERE owner = ? AND state = 'synced'
          ORDER BY created_at DESC, id LIMIT -1 OFFSET 30)
      `, job.owner);
    }
  }));
  changed(state === 'synced');
}

export async function retry(owner: string, id: string) {
  await mutate(db => db.runAsync(`
    UPDATE jobs SET state = 'pending', next_at = 0
    WHERE owner = ? AND id = ? AND ((state = 'retry_wait' AND reason != 'rate') OR
      (state = 'needs_action' AND reason IN ('gateway','unavailable')))
  `, owner, id));
  changed();
}

export async function discard(owner: string, id: string) {
  await mutate(db => db.runAsync("DELETE FROM jobs WHERE owner = ? AND id = ? AND state != 'sending'", owner, id));
  changed();
}

export async function clearAccount(owner: string, allowDraftDeletion: boolean) {
  if (!owner) return;
  ownerGenerations.set(owner, generation(owner) + 1);
  await mutate(db => db.withExclusiveTransactionAsync(async transaction => {
    if (!allowDraftDeletion && await transaction.getFirstAsync(
      "SELECT 1 FROM jobs WHERE owner = ? AND state != 'synced' LIMIT 1", owner)) {
      throw new Error('В очереди есть материалы. Подтвердите удаление перед выходом.');
    }
    await transaction.runAsync('DELETE FROM snapshots WHERE owner = ?', owner);
    await transaction.runAsync('DELETE FROM jobs WHERE owner = ?', owner);
  }));
  changed();
}

export async function saveSnapshot(db: Pick<SQLiteDatabase, 'runAsync'>, owner: string, path: string, value: unknown) {
  await db.runAsync(`
    INSERT INTO snapshots(owner,path,payload,updated_at) VALUES(?,?,?,?)
    ON CONFLICT(owner,path) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
  `, owner, path, JSON.stringify(value), Date.now());
  await db.runAsync(`
    DELETE FROM snapshots WHERE owner = ? AND path IN (
      SELECT path FROM snapshots WHERE owner = ? AND path != '/categories'
      ORDER BY updated_at DESC, path LIMIT -1 OFFSET 60
    )
  `, owner, owner);
}

// Account deletion also discards unassigned drafts on this device.
export async function clearDeletedAccount(owner: string) {
  ownerGenerations.set(owner, generation(owner) + 1);
  await mutate(db => db.withExclusiveTransactionAsync(async transaction => {
    await transaction.runAsync('DELETE FROM snapshots WHERE owner = ?', owner);
    await transaction.runAsync('DELETE FROM jobs WHERE owner IN (?, ?)', owner, unassigned);
  }));
  changed();
}
