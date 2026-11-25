import * as DocumentPicker from 'expo-document-picker';
import { File } from 'expo-file-system';
import { ApiError } from '../auth/api';
import { translate } from '../i18n';
import { errorMessage, type Request } from './model';

const maxBytes = 2 * 1024 * 1024;
const countFields = ['materials', 'duplicates', 'categories', 'tags', 'collections', 'memberships'] as const;

export type ImportSummary = Record<typeof countFields[number], number> & { replayed: boolean };
export type ImportFile = { name: string; bytes: ArrayBuffer };
class InvalidImportFile extends Error {}

export async function pickImportFile(): Promise<ImportFile | null> {
  // Some system providers classify JSON as generic binary.
  const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, base64: false });
  if (result.canceled) return null;
  const asset = result.assets[0];
  const local = asset.file ? null : new File(asset.uri);
  try {
    if (!/\.json$/i.test(asset.name)) throw new InvalidImportFile('Выберите файл выгрузки с расширением .json.');
    const size = asset.file?.size ?? local?.size ?? 0;
    if (size > maxBytes) throw new InvalidImportFile('Размер файла превышает 2 МиБ.');
    if (!size) throw new InvalidImportFile('Файл пуст или недоступен.');
    const bytes = asset.file ? await asset.file.arrayBuffer() : (await local!.bytes()).buffer;
    if (bytes.byteLength > maxBytes) throw new InvalidImportFile('Размер файла превышает 2 МиБ.');
    return { name: asset.name, bytes };
  } finally {
    if (local?.exists) local.delete();
  }
}

export async function submitImport(request: Request, mode: 'preview' | 'apply', file: ImportFile) {
  const value = await request(`/mobile/library/imports/${mode}`, 'POST', file.bytes) as Partial<ImportSummary> | null;
  if (!value || typeof value.replayed !== 'boolean' ||
      countFields.some(field => !Number.isSafeInteger(value[field]) || value[field]! < 0)) throw new ApiError(502);
  return value as ImportSummary;
}

export function importError(error: unknown, applying: boolean) {
  if (error instanceof InvalidImportFile) return error.message;
  if (!(error instanceof ApiError)) return 'Не удалось прочитать файл. Выберите выгрузку ещё раз.';
  if (error.gateway) return error.message;
  if (error.status === 0 || error.status >= 500) return applying
    ? 'Результат пока неизвестен. Восстановите подключение и повторите импорт этого файла.'
    : 'Не удалось проверить файл. Проверьте подключение и повторите.';
  if (error.status === 404) return 'На сервере ещё недоступен импорт.';
  if (error.status === 413) return 'Размер файла превышает 2 МиБ.';
  if (error.status === 415 || error.code === 'invalid_json') return 'Файл повреждён или не является JSON-выгрузкой.';
  if (error.code === 'unsupported_export_version') return 'Поддерживается только выгрузка Teleiosis версии 1.';
  if (error.code === 'group_limit_reached') return 'После импорта будет превышена квота тегов или коллекций.';
  if (error.status === 409) return 'Библиотека изменилась во время импорта. Повторите проверку файла.';
  if (error.status === 422) {
    const path = error.location.reduce<string>((text, part) =>
      typeof part === 'number' ? `${text}[${part + 1}]` : [text, part].filter(Boolean).join('.'), '');
    return path ? translate('Проверьте данные или лимиты файла ({0}).', path) : 'Проверьте данные и лимиты файла.';
  }
  return errorMessage(error);
}
