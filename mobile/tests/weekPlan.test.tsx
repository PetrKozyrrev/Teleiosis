import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import PlanRoute from '../src/app/plan';
import { ApiError } from '../src/auth/api';
import type { Request } from '../src/library/model';
import { shiftDay, validDay, type Week } from '../src/plan/model';

jest.mock('../src/offline/store', () => ({ ownerKey: () => 'synthetic' }));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
jest.mock('../src/library/ui', () => ({
  ...jest.requireActual<typeof import('../src/library/ui')>('../src/library/ui'),
  LibraryAccess: ({ children }: { children: (request: Request) => React.ReactNode }) => children(mockRequest),
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), dismissTo: jest.fn() }, useLocalSearchParams: () => ({ id: '7', goalId: mockGoalId }),
  useFocusEffect: (cb: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(cb, [cb]),
}));
const mockRequest = jest.fn<Request>();
let mockGoalId: string | undefined;
const week: Week = {
  week: '2026-11-16', end: '2026-11-22', today: '2026-11-22', budget: 30, goals: [{ id: 2, name: 'Reading' }],
  tasks: [{ id: 3, goal_id: 2, goal_name: 'Reading', content_id: 8, title: 'Synthetic task', day: '2026-11-16', minutes: 50, priority: 2, version: 2, completed_at: null }],
  summary: { total: 2, done: 1, planned_minutes: 60, done_minutes: 10, next_id: 3 },
};
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
beforeEach(() => {
  mockGoalId = undefined;
  mockRequest.mockReset().mockImplementation(async path => path === '/contents/7' ? { title: 'Synthetic note' } : week);
});

test('uses the goal selected in goal detail when scheduling a material', async () => {
  mockGoalId = '42';
  mockRequest.mockImplementation(async path => path === '/contents/7' ? { title: 'Synthetic note' }
    : { ...week, goals: [...week.goals, { id: 42, name: 'Python' }] });
  await render(<PlanRoute />);
  expect(screen.getByRole('button', { name: 'Цель · Python' })).toBeTruthy();
  await fireEvent.changeText(screen.getByLabelText('Длительность в минутах'), '15');
  await press('Запланировать материал');
  expect(mockRequest).toHaveBeenCalledWith('/mobile/plan/tasks', 'POST', {
    goal_id: 42, content_id: 7, day: '2026-11-22', minutes: 15, priority: 2,
  });
});

test('uses the configured count-based progress and requires a manual duration', async () => {
  await render(<PlanRoute />);
  expect(screen.getByText('Выполнено 1 из 2 · 50 %')).toBeTruthy();
  expect(screen.getByText(/План превышает бюджет на 30 мин/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Запланировать материал' }).props.accessibilityState.disabled).toBe(true);
  await fireEvent.changeText(screen.getByLabelText('Длительность в минутах'), '22');
  await press('Запланировать материал');
  expect(mockRequest).toHaveBeenCalledWith('/mobile/plan/tasks', 'POST', {
    goal_id: 2, content_id: 7, day: '2026-11-22', minutes: 22, priority: 2,
  });
});

test.each([412, 0, 401])('requires a fresh read after a rejected completion (%s)', async status => {
  await render(<PlanRoute />);
  mockRequest.mockRejectedValueOnce(new ApiError(status));
  await press('Завершить задание');
  expect(mockRequest).toHaveBeenLastCalledWith('/mobile/plan/tasks/3/complete', 'PUT', undefined, { version: 2 });
  expect(screen.getByRole('button', { name: 'Завершить задание' }).props.accessibilityState.disabled).toBe(true);
  expect(mockRequest.mock.calls.filter(call => call[1] === 'PUT')).toHaveLength(1);
  await press('Обновить план');
  expect(screen.getByRole('button', { name: 'Завершить задание' }).props.accessibilityState.disabled).toBe(false);
});

test('ignores a previous load after refresh', async () => {
  let resolve!: (value: unknown) => void;
  mockRequest.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  await render(<PlanRoute />);
  await press('Обновить план');
  await act(async () => resolve({ ...week, summary: { ...week.summary, done: 0 } }));
  expect(screen.getByText('Выполнено 1 из 2 · 50 %')).toBeTruthy();
});

test('calendar navigation across year boundaries and leap dates', () => {
  expect(shiftDay('2026-12-28', 7)).toBe('2027-01-04');
  expect(validDay('2028-02-29')).toBe(true);
  expect(validDay('2026-02-29')).toBe(false);
  expect(validDay('2026-11-31')).toBe(false);
});
