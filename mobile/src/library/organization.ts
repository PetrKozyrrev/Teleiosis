import { ApiError, type LibraryPath } from '../auth/api';
import { errorMessage, type Category } from './model';

export type GroupKind = 'tags' | 'collections';
export type Group = Category;
export type GroupRef = Pick<Group, 'id' | 'name'>;
export type Organization = { content_id: number; version: number; tags: GroupRef[]; collections: GroupRef[] };
export const groupLabels = { tags: 'Теги', collections: 'Коллекции' };
export const groupPath = (kind: GroupKind): LibraryPath => `/mobile/library/${kind}`;
export const organizationPath = (id: number): LibraryPath => `/mobile/library/contents/${id}/organization`;

export function organizationError(error: unknown, loading = false) {
  if (error instanceof ApiError && !error.gateway) {
    if (error.status === 404) return loading
      ? 'Теги и коллекции пока недоступны на сервере. Требуется обновление сервера; обычная библиотека продолжает работать.'
      : 'Материал, тег или коллекция больше недоступны. Обновите список.';
    if (error.status === 409) return error.code === 'group_limit_reached'
      ? 'Достигнут лимит: 200 тегов или 200 коллекций. Удалите ненужные.'
      : 'Такое название уже используется. Выберите другое или обновите список.';
    if (error.status === 412) return 'Материал уже изменён. Загрузите актуальные теги и коллекции перед сохранением.';
    if (error.status === 422) return 'Проверьте название (1–50 символов) и выбор: не более 20 тегов и 20 коллекций.';
  }
  return errorMessage(error);
}
