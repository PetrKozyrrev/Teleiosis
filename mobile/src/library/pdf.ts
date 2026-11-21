import { randomUUID } from 'expo-crypto';
import * as DocumentPicker from 'expo-document-picker';
import { Directory, File, Paths } from 'expo-file-system';
import { ApiError } from '../auth/api';
import { errorMessage, type Request } from './model';

export const pdfSizeLimit = 10 * 1024 * 1024;

export type PdfMetadata = { name: string; size_bytes: number; published: boolean };
export type SelectedPdf = { name: string; bytes: ArrayBuffer };

class PdfFileError extends Error {}

export function pdfPath(id: number) {
  return `/mobile/library/contents/${id}/pdf` as const;
}

export async function pickPdf(): Promise<SelectedPdf | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: 'application/pdf', copyToCacheDirectory: true, base64: false,
  });
  if (result.canceled) return null;
  const asset = result.assets[0];
  const local = asset.file ? null : new File(asset.uri);
  try {
    const name = asset.name.trim();
    if (!/\.pdf$/i.test(name)) throw new PdfFileError('Выберите файл с расширением .pdf.');
    const size = asset.file?.size ?? local?.size ?? 0;
    if (!size) throw new PdfFileError('Файл пуст или недоступен.');
    if (size > pdfSizeLimit) throw new PdfFileError('Размер PDF превышает 10 МиБ.');
    const bytes = asset.file ? await asset.file.arrayBuffer() : (await local!.bytes()).buffer;
    if (bytes.byteLength > pdfSizeLimit) throw new PdfFileError('Размер PDF превышает 10 МиБ.');
    return { name, bytes };
  } finally {
    if (local?.exists) local.delete();
  }
}

export const pdfCreatePath = '/mobile/library/pdf';

export async function createPdf(request: Request, selected: SelectedPdf, title: string, category: number | null) {
  const path = category === null ? pdfCreatePath : `${pdfCreatePath}?category_id=${category}` as const;
  const result = await request(path, 'POST', selected.bytes, { pdfFilename: selected.name, pdfTitle: title }) as { id?: number } | null;
  if (!result || typeof result.id !== 'number' || !Number.isSafeInteger(result.id) || result.id < 1) throw new ApiError(502);
  return result.id;
}

export async function readPdf(request: Request, id: number): Promise<PdfMetadata> {
  const result = await request(pdfPath(id), 'GET') as Partial<PdfMetadata> | null;
  if (!result || typeof result.name !== 'string' || result.published !== true ||
    typeof result.size_bytes !== 'number' || !Number.isSafeInteger(result.size_bytes) ||
    result.size_bytes < 1 || result.size_bytes > pdfSizeLimit) throw new ApiError(502);
  return result as PdfMetadata;
}

function previews() {
  return new Directory(Paths.cache, 'teleiosis-pdf-preview');
}

export function clearPdfPreviews() {
  try {
    const directory = previews();
    if (directory.exists) directory.delete();
  } catch { /* The next startup can retry cache cleanup. */ }
}

export function removePreview(file: File | null) {
  try {
    if (file?.exists) file.delete();
  } catch { /* The next startup can retry cache cleanup. */ }
}

export function writePdfPreview(bytes: ArrayBuffer): File {
  const directory = previews();
  directory.create({ idempotent: true, intermediates: true });
  const file = new File(directory, `teleiosis-${randomUUID()}.pdf`);
  try {
    file.create();
    file.write(new Uint8Array(bytes));
    return file;
  } catch {
    removePreview(file);
    throw new PdfFileError('Не удалось подготовить PDF для просмотра.');
  }
}

export function pdfError(error: unknown, creating = false) {
  if (error instanceof PdfFileError) return error.message;
  if (!(error instanceof ApiError)) return 'Не удалось открыть или прочитать PDF на устройстве.';
  if (error.gateway) return error.message;
  switch (error.code) {
    case 'pdf_disabled': return 'Создание PDF-материалов ещё не включено на сервере.';
    case 'pdf_required': return 'Выберите PDF.';
    case 'pdf_too_large': return 'Размер PDF превышает 10 МиБ.';
    case 'pdf_duplicate': return 'Этот PDF уже прикреплён к другому материалу.';
    case 'pdf_missing': return 'PDF-файл этого материала недоступен.';
    case 'pdf_quota': return 'Достигнут лимит 20 PDF или 100 МиБ. После удаления дождитесь очистки хранилища.';
    case 'pdf_removed': return 'Загрузка прервалась. Повторите с тем же файлом.';
    case 'pdf_service_unavailable': return 'Проверка или хранилище временно недоступны. Повторите с тем же файлом.';
    case 'invalid_pdf':
    case 'unsupported_pdf': return 'Нужен исправный PDF без шифрования, вложенных файлов и активных элементов.';
    case 'invalid_pdf_name': return 'Проверьте имя файла. Допускается до 120 символов с расширением .pdf.';
    case 'invalid_pdf_title': return 'Проверьте название материала. Допускается до 300 символов.';
    case 'unsafe_pdf': return 'Антивирусная проверка отклонила файл.';
    case 'pdf_busy': return 'Сервер обрабатывает другие PDF. Повторите через несколько секунд.';
  }
  if (error.status === 404) return creating ? 'Сервер пока не поддерживает создание PDF-материалов.' : 'Материал недоступен.';
  if (error.status === 0) return 'Для работы с PDF требуется подключение к серверу.';
  return errorMessage(error);
}
