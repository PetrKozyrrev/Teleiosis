import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import ReviewRoute from '../src/app/review';
import { ApiError } from '../src/auth/api';
import { router } from 'expo-router';
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
  router: { push: jest.fn(), dismissTo: jest.fn() }, useLocalSearchParams: () => mockSession ? { mode: 'session' } : { id: '7' },
  useFocusEffect: (cb: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(cb, [cb]),
}));
const mockRequest = jest.fn<Request>();
let mockSession: boolean;
const card = { id: 3, content_id: 7, title: 'Synthetic source', question: 'Synthetic question',
  answer: 'Hidden answer', takeaway: 'Synthetic takeaway', due_on: '2026-11-22', paused: false, version: 2, stage: 1 };
const result = { items: [card], total: 1, today: '2026-11-22' };
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
beforeEach(() => { mockSession = false; mockRequest.mockReset().mockResolvedValue(result); });

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

test('sequential round keeps again cards for a voluntary next round and recounts on the server', async () => {
  mockSession = true;
  const second = { ...card, id: 4, question: 'Second question' };
  mockRequest.mockResolvedValueOnce({ ...result, items: [card, second], total: 2 })
    .mockResolvedValueOnce({})
    .mockResolvedValueOnce({})
    .mockResolvedValue(result);
  await render(<ReviewRoute />);
  expect(screen.getByText('Карточка 1 из 2')).toBeTruthy();
  expect(screen.queryByText(second.question)).toBeNull();
  await press('Показать ответ');
  await press('Не помню');
  expect(screen.getByText('Карточка 2 из 2')).toBeTruthy();
  expect(screen.queryByText(card.question)).toBeNull();
  await press('Показать ответ');
  await press('Помню');
  expect(screen.getByText('Обработано карточек: 2')).toBeTruthy();
  expect(screen.getByText('Осталось к повторению: 1')).toBeTruthy();
  expect(mockRequest).toHaveBeenLastCalledWith('/mobile/review?due=true&offset=0&limit=1', 'GET');
  await press('Ещё один раунд');
  expect(screen.getByText('Карточка 1 из 1')).toBeTruthy();
  expect(screen.queryByText(card.answer)).toBeNull();
  await press('На сегодня');
  expect(mockRequest.mock.calls.filter(call => call[1] === 'POST')).toHaveLength(2);
  expect(router.dismissTo).toHaveBeenCalledWith('/');
});

test('does not advance after timeout, ignores repeated taps and retries the same operation', async () => {
  mockSession = true;
  let reject!: (error: ApiError) => void;
  mockRequest.mockResolvedValueOnce(result)
    .mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }))
    .mockResolvedValueOnce({})
    .mockResolvedValueOnce({ ...result, items: [], total: 0 });
  await render(<ReviewRoute />);
  await press('Показать ответ');
  const rate = screen.getByRole('button', { name: 'Помню' });
  await fireEvent.press(rate);
  await fireEvent.press(rate);
  expect(mockRequest.mock.calls.filter(call => call[1] === 'POST')).toHaveLength(1);
  await act(async () => reject(new ApiError(0)));
  expect(screen.getByText('Карточка 1 из 1')).toBeTruthy();
  expect(screen.queryByText('Раунд завершён')).toBeNull();
  await press('Повторить отправку оценки');
  expect(mockRequest.mock.calls[2]).toEqual(mockRequest.mock.calls[1]);
  expect(screen.getByText('Осталось к повторению: 0')).toBeTruthy();
});

test('snapshots multiple pages before revealing any card', async () => {
  mockSession = true;
  const items = Array.from({ length: 50 }, (_, index) => ({ ...card, id: index + 1 }));
  mockRequest.mockResolvedValueOnce({ ...result, items, total: 51 })
    .mockResolvedValueOnce({ ...result, items: [{ ...card, id: 51 }], total: 51 });
  await render(<ReviewRoute />);
  expect(screen.getByText('Карточка 1 из 51')).toBeTruthy();
  expect(mockRequest).toHaveBeenLastCalledWith('/mobile/review?due=true&offset=50&limit=50', 'GET');
  expect(screen.getAllByRole('button', { name: 'Показать ответ' })).toHaveLength(1);
});

test('shows an empty review round with no rating action', async () => {
  mockSession = true;
  mockRequest.mockResolvedValueOnce({ ...result, items: [], total: 0 });
  await render(<ReviewRoute />);
  expect(screen.getByRole('header', { name: 'Карточек к повторению пока нет.' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Показать ответ' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Ещё один раунд' })).toBeNull();
  expect(mockRequest).toHaveBeenCalledTimes(1);
});

test('can skip a stale card without writing another rating and keeps management available', async () => {
  mockSession = true;
  mockRequest.mockResolvedValueOnce(result)
    .mockRejectedValueOnce(new ApiError(412))
    .mockResolvedValueOnce({ ...result, items: [], total: 0 });
  await render(<ReviewRoute />);
  await press('Показать ответ');
  await press('Помню');
  expect(screen.getByText('Карточка 1 из 1')).toBeTruthy();
  await press('Пропустить карточку');
  expect(screen.getByText('Обработано карточек: 0')).toBeTruthy();
  expect(mockRequest.mock.calls.filter(call => call[1] === 'POST')).toHaveLength(1);
  await press('Управление карточками');
  expect(router.push).toHaveBeenCalledWith('/review');
});
