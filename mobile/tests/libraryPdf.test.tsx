import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import { useAuth } from '../src/auth/context';
import type { AuthController, AuthState } from '../src/auth/controller';
import type { Request } from '../src/library/model';
import { writePdfPreview } from '../src/library/pdf';
import PdfRoute from '../src/app/library/pdf';

jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('../src/offline/store', () => ({ ownerKey: (_origin: string, id: number) => String(id) }));
jest.mock('expo-router', () => ({ useLocalSearchParams: () => ({ id: '9' }), router: { push: jest.fn() } }));
jest.mock('../src/library/pdf', () => ({
  ...jest.requireActual<typeof import('../src/library/pdf')>('../src/library/pdf'),
  writePdfPreview: jest.fn(), removePreview: jest.fn(),
}));

const request = jest.fn<Request>();
const bytes = new Uint8Array([37, 80, 68, 70]).buffer;
const selected = { name: 'fixture.pdf', bytes };
const metadata = { name: selected.name, size_bytes: bytes.byteLength, published: true };
const path = '/mobile/library/contents/9/pdf';
let state: AuthState;
let generation: number;

function press(name: string) {
  return fireEvent.press(screen.getByRole('button', { name }));
}

beforeEach(() => {
  generation = 1;
  request.mockReset();
  jest.mocked(writePdfPreview).mockClear();
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

test('never writes a preview after the active session expires', async () => {
  let finish!: (data: ArrayBuffer) => void;
  request.mockReset().mockResolvedValueOnce(metadata)
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const rendered = await render(<PdfRoute />);
  await press('Открыть PDF');
  expect(request).toHaveBeenLastCalledWith(`${path}/download`, 'GET');
  generation += 1;
  state = { phase: 'signedOut', session: null, message: 'Сессия завершилась.', busy: false };
  await rendered.rerender(<PdfRoute />);
  await act(async () => { finish(bytes); });
  expect(jest.mocked(writePdfPreview)).not.toHaveBeenCalled();
  expect(screen.getByText('Сессия завершилась.')).toBeTruthy();
});
