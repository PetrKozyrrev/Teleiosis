import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import * as DocumentPicker from 'expo-document-picker';
import { File } from 'expo-file-system';
import { ApiError } from '../src/auth/api';
import { useAuth } from '../src/auth/context';
import type { AuthController, AuthState } from '../src/auth/controller';
import type { Request } from '../src/library/model';
import ImportLibrary from '../src/app/library/import';

jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn() }));
jest.mock('expo-file-system', () => ({ File: jest.fn() }));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('../src/offline/store', () => ({ ownerKey: (_origin: string, id: number) => String(id) }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));

const request = jest.fn<Request>();
const original = new Uint8Array([123, 125]);
const mockDelete = jest.fn();
const mockBytes = jest.fn<() => Promise<Uint8Array<ArrayBuffer>>>();
const mockFile = File as unknown as jest.Mock<() => Pick<File, 'size' | 'bytes' | 'exists' | 'delete'>>;
const summary = { materials: 1, duplicates: 2, categories: 3, tags: 1, collections: 2, memberships: 4, replayed: false };
let state: AuthState;
let loginGeneration: number;

function press(name: string) {
  return fireEvent.press(screen.getByRole('button', { name }));
}

beforeEach(() => {
  loginGeneration = 1;
  request.mockReset().mockResolvedValue(summary);
  mockDelete.mockClear();
  mockBytes.mockReset().mockResolvedValue(original);
  mockFile.mockImplementation(() => ({ size: 2, bytes: mockBytes, exists: true, delete: mockDelete }));
  jest.mocked(DocumentPicker.getDocumentAsync).mockReset().mockResolvedValue({
    canceled: false, assets: [{ name: 'test.json', uri: 'file:///cache/test.json', lastModified: 1 }],
  });
  state = { phase: 'signedIn', busy: false, message: null, session: {
    expires_at: '', absolute_expires_at: '', user: { id: 1, email: 'test@example.com',
      timezone: 'UTC', reminders_enabled: true, reminder_time: '10:00', email_verified_at: null },
  } };
  jest.mocked(useAuth).mockImplementation(() => ({
    state, controller: { library: request, captureSession: () => {
      const generation = loginGeneration;
      return () => generation === loginGeneration;
    } } as unknown as AuthController,
  }));
});

test('requires preview and confirmation, then retries identical bytes after a lost response', async () => {
  request.mockResolvedValueOnce(summary).mockRejectedValueOnce(new ApiError(0))
    .mockResolvedValueOnce({ ...summary, replayed: true });
  await render(<ImportLibrary />);
  await press('Выбрать файл');
  expect(mockDelete).toHaveBeenCalledTimes(1);
  expect(request).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: 'Импортировать' })).toBeNull();
  await press('Проверить файл');
  expect(screen.getByText('Предварительный результат')).toBeTruthy();
  expect(request).toHaveBeenNthCalledWith(1, '/mobile/library/imports/preview', 'POST', original.buffer);
  await press('Импортировать');
  expect(screen.getByText(/Результат пока неизвестен/)).toBeTruthy();
  await press('Импортировать');
  expect(request).toHaveBeenNthCalledWith(2, '/mobile/library/imports/apply', 'POST', original.buffer);
  expect(request).toHaveBeenNthCalledWith(3, '/mobile/library/imports/apply', 'POST', original.buffer);
  expect(screen.getByText(/Этот файл уже был импортирован/)).toBeTruthy();
  expect(screen.queryByText('test.json')).toBeNull();
});

test('rejects an oversized file before reading it and cleans the copy', async () => {
  mockFile.mockImplementationOnce(() => ({
    size: 2 * 1024 * 1024 + 1, bytes: mockBytes, exists: true, delete: mockDelete,
  }));
  await render(<ImportLibrary />);
  await press('Выбрать файл');
  expect(screen.getByText('Размер файла превышает 2 МиБ.')).toBeTruthy();
  expect(mockBytes).not.toHaveBeenCalled();
  expect(mockDelete).toHaveBeenCalledTimes(1);
  expect(request).not.toHaveBeenCalled();
});

test('shows validation location and offers no apply action', async () => {
  request.mockRejectedValueOnce(new ApiError(422, false, null, null, 'invalid_export_field', ['contents', 0, 'title']));
  await render(<ImportLibrary />);
  await press('Выбрать файл');
  await press('Проверить файл');
  expect(screen.getByText(/contents\[1\].title/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Импортировать' })).toBeNull();
});

test('discards the pending file and stale preview when the session expires', async () => {
  let finish!: (value: typeof summary) => void;
  request.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const rendered = await render(<ImportLibrary />);
  await press('Выбрать файл');
  await press('Проверить файл');
  loginGeneration += 1;
  state = { phase: 'signedOut', session: null, message: 'Сессия завершилась. Войдите заново.', busy: false };
  await rendered.rerender(<ImportLibrary />);
  await act(async () => { finish(summary); });
  expect(screen.getByText('Сессия завершилась. Войдите заново.')).toBeTruthy();
  expect(screen.queryByText('test.json')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Импортировать' })).toBeNull();
});
