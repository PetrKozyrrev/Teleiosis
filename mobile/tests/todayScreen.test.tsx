import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import TodayScreen from '../src/app/(tabs)/index';
import { ApiError } from '../src/auth/api';
import { useAuth } from '../src/auth/context';
import type { AuthController } from '../src/auth/controller';
import { saveLanguage } from '../src/i18n';
import type { Request } from '../src/library/model';

jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: { getItem: async () => null, setItem: async () => {} },
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), navigate: jest.fn() },
  useFocusEffect: (callback: () => void) =>
    jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback, mockFocus]),
}));
jest.mock('../src/auth/config', () => ({
  ...jest.requireActual<typeof import('../src/auth/config')>('../src/auth/config'), API_ORIGIN: 'https://example.com',
}));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('../src/offline/store', () => ({
  generation: () => 0,
  ownerKey: (origin: string, id: number) => `${origin}/${id}`,
  subscribe: () => () => {},
  database: async () => ({ getFirstAsync: mockSnapshot }),
  mutate: async () => {},
}));

const request = jest.fn<Request>();
const mockSnapshot = jest.fn<(query: string, owner: string, path: string) => Promise<unknown>>();
const controller = { library: request, captureSession: () => () => true } as unknown as AuthController;
const path = '/mobile/learning/today';
const materialTitle = 'Тестовая статья';
const data = {
  local_date: '2026-11-26', library_state: 'available',
  next_action: { material_id: 42, task_day: null, title: materialTitle, content_type: 'article',
    source: 'web', reason: 'unseen_material', duration_minutes: null },
  due_review_count: 2,
  weekly_progress: { weekly_goal: 4, weekly_completed: 1, tasks_total: 2, tasks_done: 1 },
};
let mockFocus = 0;

function account(id: number) {
  jest.mocked(useAuth).mockReturnValue({
    controller,
    state: { phase: 'signedIn', busy: false, message: null, session: {
      user: { id, email: 'synthetic@example.com', timezone: 'Europe/Moscow', reminders_enabled: false,
        reminder_time: '09:00', email_verified_at: null },
      expires_at: '', absolute_expires_at: '',
    } },
  });
}

const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));

beforeEach(() => {
  mockFocus = 0;
  request.mockReset().mockResolvedValue(data);
  mockSnapshot.mockReset().mockResolvedValue(null);
  jest.mocked(router.push).mockClear();
  jest.mocked(router.navigate).mockClear();
  account(1);
});

test('shows next action and opens the existing detail, review, progress, add, plan and library screens', async () => {
  await render(<TodayScreen />);
  expect(request).toHaveBeenCalledWith(path, 'GET');
  expect(screen.getByRole('header', { name: 'Сегодня' })).toBeTruthy();
  expect(screen.getByText(materialTitle)).toBeTruthy();
  expect(screen.getByText('Сайт · Время неизвестно')).toBeTruthy();
  expect(screen.getByText('Следующий непросмотренный материал')).toBeTruthy();
  expect(screen.getByText('Доступно карточек: 2')).toBeTruthy();
  expect(screen.getByText('Изучено 1 из 4 материалов')).toBeTruthy();
  expect(screen.getByText('Задания недели: выполнено 1 из 2')).toBeTruthy();
  await press('Открыть материал');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/library/[id]', params: { id: '42' } });
  await press('Повторение');
  expect(router.push).toHaveBeenCalledWith('/review');
  await press('План');
  expect(router.push).toHaveBeenCalledWith('/plan');
  await press('Прогресс');
  expect(router.navigate).toHaveBeenCalledWith('/progress');
  await press('Добавить');
  expect(router.navigate).toHaveBeenCalledWith('/add-link');
  await press('Вся библиотека');
  expect(router.navigate).toHaveBeenCalledWith('/library');
});

test.each([
  ['empty', 'Сохраните первый материал, чтобы начать обучение.'],
  ['scheduled_later', 'Следующее занятие запланировано на другой день.'],
  ['no_recommendation', 'Можно выбрать материал в библиотеке или сохранить новый.'],
])('shows the %s state and a neutral empty review queue', async (library_state, heading) => {
  request.mockResolvedValue({ ...data, library_state, next_action: null, due_review_count: 0 });
  await render(<TodayScreen />);
  expect(screen.getByText(heading)).toBeTruthy();
  expect(screen.getByText('Пока нет карточек для повторения.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Добавить' })).toBeTruthy();
  expect(screen.queryByText(materialTitle)).toBeNull();
});

test('keeps available sections with a partial response and reloads on focus', async () => {
  request.mockResolvedValueOnce({ next_action: data.next_action });
  const view = await render(<TodayScreen />);
  expect(screen.getByText(materialTitle)).toBeTruthy();
  expect(screen.getByText('Количество доступных карточек неизвестно.')).toBeTruthy();
  expect(screen.getByText('Недельный прогресс недоступен.')).toBeTruthy();
  expect(screen.queryByText('Пока нет карточек для повторения.')).toBeNull();

  mockFocus++;
  await view.rerender(<TodayScreen />);
  expect(request).toHaveBeenCalledTimes(2);
  expect(screen.getByText('Доступно карточек: 2')).toBeTruthy();
});

test('shows connectivity errors and lets the user retry', async () => {
  request.mockRejectedValueOnce(new ApiError(0));
  await render(<TodayScreen />);
  expect(screen.getByText('Нет связи с сервером. Данные экрана «Сегодня» недоступны.')).toBeTruthy();
  expect(screen.queryByText('Пока нет карточек для повторения.')).toBeNull();
  await press('Повторить');
  expect(screen.getByText(materialTitle)).toBeTruthy();
});

test('only uses the offline snapshot for its owner and discards the previous account response', async () => {
  request.mockRejectedValueOnce(new ApiError(0));
  mockSnapshot.mockImplementation(async (_query, owner, requested) =>
    owner === 'https://example.com/1' && requested === path
      ? { payload: JSON.stringify(data), updated_at: Date.UTC(2026, 10, 24) } : null);
  const view = await render(<TodayScreen />);
  expect(screen.getByText(/Данные могут быть устаревшими/)).toBeTruthy();
  expect(screen.getByText(materialTitle)).toBeTruthy();

  let completeFirst!: (value: unknown) => void;
  request.mockImplementationOnce(() => new Promise(resolve => { completeFirst = resolve; }));
  await press('Обновить');
  account(2);
  request.mockRejectedValueOnce(new ApiError(0));
  await view.rerender(<TodayScreen />);
  expect(mockSnapshot).toHaveBeenLastCalledWith(expect.any(String), 'https://example.com/2', path);
  expect(screen.queryByText(materialTitle)).toBeNull();
  await act(async () => completeFirst(data));
  expect(screen.queryByText(materialTitle)).toBeNull();
  expect(screen.queryByText(/Данные могут быть устаревшими/)).toBeNull();
});

test('passes a specific task from Today to the material without changing library entry points', async () => {
  request.mockResolvedValue({ ...data, next_action: {
    ...data.next_action, task_id: 7, task_day: '2026-11-24', reason: 'studied_task', goal_name: 'Точная цель',
  } });
  await render(<TodayScreen />);
  expect(screen.getByText('Из плана на 24 ноября')).toBeTruthy();
  expect(screen.getByText('Цель: Точная цель')).toBeTruthy();
  await press('Открыть материал');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/library/[id]', params: { id: '42', taskId: '7' } });
});

test('starts every preset in one tap and offers a neutral alternative route', async () => {
  await render(<TodayScreen />);
  for (const minutes of ['5', '15', '30', '60']) {
    await press(`${minutes} мин`);
    expect(router.push).toHaveBeenLastCalledWith({ pathname: '/time-budget', params: { minutes } });
  }
  await press('Выбрать другое');
  expect(router.push).toHaveBeenLastCalledWith('/time-budget');
});

test('localizes the plan date and controls without shortening the content title', async () => {
  const title = 'A long material title '.repeat(8).trim();
  request.mockResolvedValue({ ...data, next_action: {
    ...data.next_action, title, task_id: 7, task_day: '2026-11-24', reason: 'overdue_task',
  } });
  await saveLanguage('en');
  try {
    await render(<TodayScreen />);
    expect(screen.getByRole('header', { name: title })).toBeTruthy();
    expect(screen.getByText('From the plan for November 24')).toBeTruthy();
    expect(screen.getByRole('button', { name: '15 min' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Choose another' })).toBeTruthy();
  } finally {
    await act(async () => saveLanguage('ru'));
  }
});
