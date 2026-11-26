import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import { ApiError } from '../src/auth/api';
import { TimeBudget } from '../src/learning/TimeBudget';
import type { Request } from '../src/library/model';

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), dismissTo: jest.fn() },
  useFocusEffect: (callback: () => void) =>
    jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback, mockFocus]),
}));
jest.mock('../src/offline/store', () => ({
  generation: () => 0,
  subscribe: () => () => {},
  database: async () => ({ getFirstAsync: mockSnapshot }),
  mutate: async () => {},
}));

const owner = 'https://example.com/1';
const path = '/mobile/learning/time-budget?budget_minutes=';
const item = { material_id: 42, title: 'Тестовый материал', source: 'web', status: 'planned',
  content_type: 'article', duration_minutes: 5, reason: 'today_task', goal_name: 'Цель',
  task_id: 7, task_day: '2026-11-26' };
const response = (budget: number, items = [item], unknown = false) => ({
  budget_minutes: budget, local_date: '2026-11-26', items, has_unknown_duration: unknown,
});
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
const mockSnapshot = jest.fn<(query: string, owner: string, path: string) => Promise<unknown>>();
let mockFocus = 0;

beforeEach(() => {
  mockFocus = 0;
  mockSnapshot.mockReset().mockResolvedValue(null);
});

test('requests each preset, shows a known estimate and opens the material with task context', async () => {
  const request = jest.fn<Request>().mockImplementation(async url => response(Number(url.split('=').at(-1))));
  await render(<TimeBudget request={request} owner={owner} />);
  expect(request).not.toHaveBeenCalled();
  for (const minutes of [5, 15, 30, 60] as const) {
    await press(`${minutes} мин`);
    expect(request).toHaveBeenLastCalledWith(`${path}${minutes}`, 'GET');
    expect(screen.getByRole('button', { name: `${minutes} мин` }).props.accessibilityState.selected).toBe(true);
  }
  expect(screen.getByText('Запланировано · Сайт · ≈ 5 мин')).toBeTruthy();
  expect(screen.getByText('Цель: Цель')).toBeTruthy();
  await press('Открыть материал');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/library/[id]', params: { id: '42', taskId: '7' } });
  await press('Вся библиотека');
  expect(router.dismissTo).toHaveBeenCalledWith('/library');
});

test('a slower previous budget cannot replace the current results', async () => {
  let resolveFirst!: (value: unknown) => void;
  const request = jest.fn<Request>().mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve; }))
    .mockResolvedValue(response(15, [], true));
  await render(<TimeBudget request={request} owner={owner} />);
  await press('5 мин');
  await press('15 мин');
  expect(screen.getByText('На это время подходящих материалов нет.')).toBeTruthy();
  expect(screen.getByText('Попробуйте выбрать больше времени.')).toBeTruthy();
  expect(screen.getByText('Есть материалы без оценки времени')).toBeTruthy();
  await act(async () => resolveFirst(response(5)));
  expect(screen.queryByText(item.title)).toBeNull();
});

test('loads only the active owner and budget snapshot, labels it stale and refreshes after returning', async () => {
  const request = jest.fn<Request>().mockRejectedValueOnce(new ApiError(0)).mockRejectedValueOnce(new ApiError(0))
    .mockResolvedValueOnce(response(15)).mockResolvedValueOnce(response(15, []));
  mockSnapshot.mockImplementation(async (_query, key, requested) => key === owner && requested === path + 5
    ? { payload: JSON.stringify(response(5)), updated_at: Date.UTC(2026, 10, 26) } : null);
  const view = await render(<TimeBudget request={request} owner={owner} />);
  await press('5 мин');
  expect(screen.getByText(/Данные могут быть устаревшими/)).toBeTruthy();
  expect(mockSnapshot).toHaveBeenLastCalledWith(expect.any(String), owner, path + 5);
  await press('15 мин');
  expect(mockSnapshot).toHaveBeenLastCalledWith(expect.any(String), owner, path + 15);
  expect(screen.queryByText(item.title)).toBeNull();
  expect(screen.getByText('Нет связи с сервером. Сохранённого подбора на это время нет.')).toBeTruthy();
  await press('Повторить');
  expect(screen.getByText(item.title)).toBeTruthy();

  mockFocus++;
  await view.rerender(<TimeBudget request={request} owner={owner} />);
  expect(screen.queryByText(item.title)).toBeNull();
  expect(screen.getByText('На это время подходящих материалов нет.')).toBeTruthy();
});
