import { ApiError, type LibraryMethod, type LibraryOptions, type LibraryPath } from '../auth/api';

export const statuses = {
  unseen: 'Не просмотрено', planned: 'Запланировано', studied: 'Изучено', irrelevant: 'Неактуально',
};
export const sources = { youtube: 'YouTube', telegram: 'Telegram', web: 'Сайт', other: 'Заметка' };
export const sorts = { newest: 'Сначала новые', oldest: 'Сначала старые', title: 'По названию' };

export type Status = keyof typeof statuses;
export type Source = keyof typeof sources;
export type Category = { id: number; name: string; contents_count: number };
export type Material = {
  id: number;
  title: string;
  url: string | null;
  description: string | null;
  note: string | null;
  category_id: number | null;
  status: Status;
  source: Source;
  open_count: number;
  created_at?: string;
  version?: number;
};
export type MaterialPage = { items: Material[]; total: number; limit: number; offset: number };
export type Request = (path: LibraryPath, method: LibraryMethod, body?: unknown, options?: LibraryOptions) => Promise<unknown>;
export type Filters = {
  q: string;
  status: Status | '';
  source: Source | '';
  category: number | 'none' | '';
  sort: keyof typeof sorts;
};
export const initialFilters: Filters = { q: '', status: '', source: '', category: '', sort: 'newest' };
export const pageSize = 20;
export const maxOffset = 1_000_000;

export function listPath({ q, status, source, category, sort }: Filters, offset: number): LibraryPath {
  const query = new URLSearchParams({ sort, limit: String(pageSize), offset: String(offset) });
  if (q.trim()) query.set('q', q.trim());
  if (status) query.set('status', status);
  if (source) query.set('source', source);
  if (category === 'none') query.set('uncategorized', 'true');
  else if (category) query.set('category_id', String(category));
  return `/contents?${query}`;
}

export function parseId(value: unknown): number | null {
  const id = Number(value);
  return typeof value === 'string' && /^[1-9][0-9]*$/.test(value) && Number.isSafeInteger(id) ? id : null;
}

export function originalUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

export function errorMessage(error: unknown, validation = 'Проверьте данные и повторите.') {
  if (!(error instanceof ApiError)) return 'Не удалось выполнить запрос. Повторите позже.';
  if (error.gateway) return error.message;
  switch (error.status) {
    case 401: return 'Сессия завершилась. Войдите заново.';
    case 404: return 'Материал или категория больше недоступны.';
    case 422: return validation;
    default: return error.message;
  }
}

export function uncertainCreate(error: unknown) {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500);
}
