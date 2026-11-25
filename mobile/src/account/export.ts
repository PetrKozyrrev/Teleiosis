import { File, Paths } from 'expo-file-system';
import { isAvailableAsync, shareAsync } from 'expo-sharing';
import type { Request } from '../library/model';
import { ApiError } from '../auth/api';
import { translate } from '../i18n';

export async function exportAccount(request: Request, isCurrent = () => true) {
  if (!await isAvailableAsync()) throw new Error('Системная отправка файлов недоступна.');
  if (!isCurrent()) throw new Error('Аккаунт изменился. Повторите выгрузку.');
  let data: unknown;
  try {
    data = await request('/me/export', 'GET');
  } catch (error) {
    if (error instanceof ApiError && error.gateway) {
      error.message = 'Выгрузка недоступна через шлюз стенда. Администратору нужно проверить настройки доступа.';
    }
    throw error;
  }
  if (!isCurrent()) throw new Error('Аккаунт изменился. Повторите выгрузку.');
  const file = new File(Paths.cache, 'teleiosis-export.json');
  try {
    file.create({ overwrite: true });
    file.write(JSON.stringify(data, null, 2));
    await shareAsync(file.uri, { mimeType: 'application/json', UTI: 'public.json', dialogTitle: translate('Выгрузка Телеосис') });
  } finally {
    if (file.exists) file.delete();
  }
}
