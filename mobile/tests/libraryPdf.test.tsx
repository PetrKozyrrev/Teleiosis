import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import { ApiError } from '../src/auth/api';
import { useAuth } from '../src/auth/context';
import type { AuthController, AuthState } from '../src/auth/controller';
import type { Material, Request } from '../src/library/model';
import { removePreview, writePdfPreview } from '../src/library/pdf';
import MaterialRoute from '../src/app/library/[id]';

jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('../src/offline/store', () => ({ ownerKey: (_origin: string, id: number) => String(id) }));
jest.mock('../src/offline/cache', () => ({ readOnline: async (_owner: unknown, request: Request, path: Parameters<Request>[0]) => ({
  value: await request(path, 'GET'),
}) }));
jest.mock('expo-router', () => ({
  useLocalSearchParams: () => ({ id: '9' }), useNavigation: () => ({ isFocused: () => true }),
  useFocusEffect: (callback: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
  router: { push: jest.fn() },
}));
jest.mock('../src/library/pdf', () => ({
  ...jest.requireActual<typeof import('../src/library/pdf')>('../src/library/pdf'),
  writePdfPreview: jest.fn(), removePreview: jest.fn(),
}));

const request = jest.fn<Request>();
const bytes = new Uint8Array([37, 80, 68, 70]).buffer;
const material: Material = { id: 9, title: 'Тестовый документ', content_type: 'pdf', url: null,
  description: null, note: null, status: 'unseen', source: 'web', category_id: null, open_count: 0, version: 1 };
const download = '/mobile/library/contents/9/pdf/download';
const preview = jest.fn<() => Promise<void>>();
const file = { preview } as unknown as ReturnType<typeof writePdfPreview>;
let state: AuthState;
let generation: number;

function press(name: string) {
  return fireEvent.press(screen.getByRole('button', { name }));
}

beforeEach(() => {
  generation = 1;
  request.mockReset().mockImplementation(async path => path === '/contents/9' ? material : []);
  preview.mockReset().mockResolvedValue(undefined);
  jest.mocked(writePdfPreview).mockReset().mockReturnValue(file);
  jest.mocked(removePreview).mockClear();
  jest.mocked(router.push).mockClear();
  state = { phase: 'signedIn', busy: false, message: null, session: {
    expires_at: '', absolute_expires_at: '', user: { id: 1, email: 'a@example.com', timezone: 'UTC',
      reminders_enabled: true, reminder_time: '10:00', email_verified_at: null },
  } };
  const controller = { library: request, captureSession: () => {
    const captured = generation;
    return () => captured === generation;
  } } as unknown as AuthController;
  jest.mocked(useAuth).mockImplementation(() => ({ state, controller }));
});

test('hands the PDF directly to the system viewer with one press and removes the temporary copy on exit', async () => {
  const rendered = await render(<MaterialRoute />);
  request.mockResolvedValueOnce(bytes);
  await press('Открыть PDF');
  expect(request).toHaveBeenLastCalledWith(download, 'GET');
  expect(writePdfPreview).toHaveBeenCalledWith(bytes);
  expect(preview).toHaveBeenCalledTimes(1);
  expect(router.push).not.toHaveBeenCalled();
  expect(removePreview).not.toHaveBeenCalledWith(file);
  await rendered.unmount();
  expect(removePreview).toHaveBeenCalledWith(file);
});

test('reports a failed download in the material card and allows another attempt', async () => {
  await render(<MaterialRoute />);
  request.mockRejectedValueOnce(new ApiError(0)).mockResolvedValueOnce(bytes);
  await press('Открыть PDF');
  expect(screen.getByText('Для работы с PDF требуется подключение к серверу.')).toBeTruthy();
  expect(preview).not.toHaveBeenCalled();
  await press('Открыть PDF');
  expect(preview).toHaveBeenCalledTimes(1);
});

test('never writes a preview after the active session expires', async () => {
  let finish!: (data: ArrayBuffer) => void;
  const rendered = await render(<MaterialRoute />);
  request.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  await press('Открыть PDF');
  expect(request).toHaveBeenLastCalledWith(download, 'GET');
  generation += 1;
  state = { phase: 'signedOut', session: null, message: 'Сессия завершилась.', busy: false };
  await rendered.rerender(<MaterialRoute />);
  await act(async () => { finish(bytes); });
  expect(jest.mocked(writePdfPreview)).not.toHaveBeenCalled();
  expect(screen.getByText('Сессия завершилась.')).toBeTruthy();
});
