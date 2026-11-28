import { ApiError, type LibraryPath } from '../auth/api';
import { pageSize, type Category, type Filters, type Material, type MaterialPage, type Request } from '../library/model';
import { database, generation, mutate, saveSnapshot } from './store';

type Snapshot = { payload: string; updated_at: number; path: string };
export type Read<T> = { value: T; cachedAt?: number };

export async function remember(owner: string, path: LibraryPath, value: unknown, expected = generation(owner)) {
  await mutate(db => db.withExclusiveTransactionAsync(async transaction => {
    if (generation(owner) === expected) await saveSnapshot(transaction, owner, path, value);
  }));
}

export async function forgetMaterial(owner: string, id: number) {
  await mutate(db => db.runAsync(`
    DELETE FROM snapshots WHERE owner = ? AND (path = ? OR (path LIKE '/contents?%' AND EXISTS (
      SELECT 1 FROM json_each(snapshots.payload, '$.items') WHERE json_extract(value, '$.id') = ?
    )) OR (path LIKE '/mobile/learning/time-budget?%' AND EXISTS (
      SELECT 1 FROM json_each(snapshots.payload, '$.items') WHERE json_extract(value, '$.material_id') = ?
    )))
  `, owner, `/contents/${id}`, id, id));
}

export async function forgetGoalRecommendations(owner: string) {
  await mutate(db => db.runAsync(
    "DELETE FROM snapshots WHERE owner = ? AND (path = '/mobile/learning/today' OR path LIKE '/mobile/learning/time-budget?%')",
    owner,
  ));
}

async function loaded(owner: string) {
  const rows = await (await database()).getAllAsync<Snapshot>(
    "SELECT * FROM snapshots WHERE owner = ? AND (path LIKE '/contents/%' OR path LIKE '/contents?%') ORDER BY updated_at DESC",
    owner);
  const items = new Map<number, Material>();
  for (const row of rows) {
    const value = JSON.parse(row.payload) as Material | MaterialPage;
    for (const material of 'items' in value ? value.items : [value]) {
      if (!items.has(material.id)) items.set(material.id, material);
    }
  }
  return { items: [...items.values()], cachedAt: rows[0]?.updated_at };
}

export function filterDownloaded(items: Material[], filters: Filters) {
  const title = new Intl.Collator('ru', { sensitivity: 'base' });
  const q = filters.q.trim().toLocaleLowerCase('ru');
  return items.filter(item =>
    (!q || item.title.toLocaleLowerCase('ru').includes(q)) &&
    (!filters.status || item.status === filters.status) &&
    (!filters.source || item.source === filters.source) &&
    (!filters.contentType || item.content_type === filters.contentType) &&
    (!filters.category || item.category_id === (filters.category === 'none' ? null : filters.category))
  ).sort((a, b) => filters.sort === 'title'
    ? title.compare(a.title, b.title) || a.id - b.id
    : (filters.sort === 'oldest' ? 1 : -1) *
      ((a.created_at ?? '').localeCompare(b.created_at ?? '') || a.id - b.id));
}

export async function readOnline<T>(owner: string | null, request: Request, path: LibraryPath,
  fallback: (owner: string) => Promise<Read<T> | null>): Promise<Read<T>> {
  const expected = owner ? generation(owner) : undefined;
  try {
    const value = await request(path, 'GET') as T;
    if (owner) await remember(owner, path, value, expected).catch(() => {});
    return { value };
  } catch (error) {
    if (!owner || generation(owner) !== expected || !(error instanceof ApiError) || (error.status !== 0 && error.status < 500)) throw error;
    const cached = await fallback(owner);
    if (!cached || generation(owner) !== expected) throw error;
    return cached;
  }
}

export async function cachedSnapshot<T>(owner: string, path: LibraryPath): Promise<Read<T> | null> {
  const row = await (await database()).getFirstAsync<Snapshot>(
    'SELECT * FROM snapshots WHERE owner = ? AND path = ?', owner, path);
  return row ? { value: JSON.parse(row.payload) as T, cachedAt: row.updated_at } : null;
}

export function cachedCategories(owner: string) {
  return cachedSnapshot<Category[]>(owner, '/categories');
}

export async function cachedMaterial(owner: string, id: number): Promise<Read<Material> | null> {
  const result = await loaded(owner);
  const item = result.items.find(material => material.id === id);
  return item ? { value: item, cachedAt: result.cachedAt } : null;
}

export async function cachedList(owner: string, filters: Filters, offset: number, limit = pageSize): Promise<Read<MaterialPage> | null> {
  if (filters.tag || filters.collection) return null;
  const result = await loaded(owner);
  if (result.cachedAt === undefined) return null;
  const items = filterDownloaded(result.items, filters);
  return { cachedAt: result.cachedAt, value: { items: items.slice(offset, offset + limit), total: items.length, limit, offset } };
}
