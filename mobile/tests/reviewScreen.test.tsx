import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import ReviewRoute from '../src/app/review';
import { ApiError } from '../src/auth/api';
import type { Request } from '../src/library/model';

jest.mock('../src/offline/store', () => ({ ownerKey: () => 'synthetic' }));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
jest.mock('expo-crypto', () => ({ randomUUID: () => '08ee2f9c-1234-4123-8123-123456789012' }));
jest.mock('../src/library/ui', () => ({
  ...jest.requireActual<typeof import('../src/library/ui')>('../src/library/ui'),
  LibraryAccess: ({ children }: { children: (request: Request) => React.ReactNode }) => children(mockRequest),
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), dismissTo: jest.fn() }, useLocalSearchParams: () => ({ id: '7' }),
  useFocusEffect: (cb: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(cb, [cb]),
}));
const mockRequest = jest.fn<Request>();
const card = { id: 3, content_id: 7, title: 'Synthetic source', question: 'Synthetic question',
  answer: 'Hidden answer', takeaway: 'Synthetic takeaway', due_on: '2026-11-22', paused: false, version: 2, stage: 1 };
const result = { items: [card], total: 1, today: '2026-11-22' };
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
beforeEach(() => { mockRequest.mockReset().mockResolvedValue(result); });

test('reveals the answer before rating and sends version and operation key once', async () => {
  await render(<ReviewRoute />);
  expect(screen.queryByText('Hidden answer')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Помню' })).toBeNull();
  await press('Показать ответ');
  expect(screen.getByText('Hidden answer')).toBeTruthy();
  await press('Помню');
  expect(mockRequest).toHaveBeenCalledWith('/mobile/review/3/answers', 'POST', { rating: 'remembered' },
    { version: 2, idempotencyKey: '08ee2f9c-1234-4123-8123-123456789012' });
});

test.each([0, 401, 412])('blocks another write after %s until explicit refresh', async status => {
  await render(<ReviewRoute />);
  await press('Показать ответ');
  mockRequest.mockRejectedValueOnce(new ApiError(status));
  await press('Не помню');
  expect(screen.getByRole('button', { name: 'Не помню' }).props.accessibilityState.disabled).toBe(true);
  expect(mockRequest.mock.calls.filter(call => call[1] === 'POST')).toHaveLength(1);
  await press('Обновить карточки');
  expect(screen.queryByRole('button', { name: 'Не помню' })).toBeNull();
});

test('retains creation key after lost response so refresh and retry cannot duplicate', async () => {
  await render(<ReviewRoute />);
  await fireEvent.changeText(screen.getByLabelText('Вопрос'), ' New question ');
  await fireEvent.changeText(screen.getByLabelText('Ответ'), ' New answer ');
  mockRequest.mockRejectedValueOnce(new ApiError(0));
  await press('Создать карточку');
  await press('Обновить карточки');
  await press('Создать карточку');
  const writes = mockRequest.mock.calls.filter(call => call[0] === '/mobile/review' && call[1] === 'POST');
  expect(writes).toHaveLength(2);
  expect(writes[0]).toEqual(writes[1]);
  expect(writes[0][2]).toEqual({ content_id: 7, question: 'New question', answer: 'New answer', takeaway: '' });
});

test('ignores an outdated list response after refresh', async () => {
  let resolve!: (value: unknown) => void;
  mockRequest.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  await render(<ReviewRoute />);
  await press('Обновить карточки');
  await act(async () => resolve({ ...result, items: [{ ...card, question: 'Old question' }] }));
  expect(screen.queryByText('Old question')).toBeNull();
  expect(screen.getByText('Synthetic question')).toBeTruthy();
});

test('paused cards can be read without accepting a rating', async () => {
  mockRequest.mockResolvedValue({ ...result, items: [{ ...card, paused: true }] });
  await render(<ReviewRoute />);
  await press('Показать ответ');
  expect(screen.getByText('Hidden answer')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Помню' })).toBeNull();
});
