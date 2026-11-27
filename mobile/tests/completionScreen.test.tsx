import { act, fireEvent, render, renderHook, screen } from '@testing-library/react-native';
import { expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import { AppState, type AppStateStatus } from 'react-native';
import { ApiError } from '../src/auth/api';
import { Completion } from '../src/learning/Completion';
import { useSourceReturn } from '../src/learning/sourceReturn';
import type { Request } from '../src/library/model';
import { reflectionDraft, saveReflectionDraft } from '../src/offline/store';

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), canGoBack: () => true, back: jest.fn() },
  useFocusEffect: (callback: () => void) =>
    jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
}));
jest.mock('expo-crypto', () => ({
  randomUUID: jest.fn(() => '1354f12f-935e-4ad3-a333-31cd72547f18'),
}));
jest.mock('../src/offline/store', () => ({
  generation: () => 1, reflectionDraft: jest.fn(), saveReflectionDraft: jest.fn(),
  clearReflectionDraft: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
}));
jest.mock('../src/offline/cache', () => ({
  forgetMaterial: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
  remember: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
}));

const path = '/mobile/learning/materials/42';
const item = { id: 42, title: 'Материал', status: 'unseen', version: 3 };
const details = { material: item, tasks: [{ id: 7, day: '2026-11-26', goal_name: 'Цель' }], reflection: null };
const done = { material: { ...item, status: 'studied', version: 4 }, task_completed: false };
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));

test('timeout never shows success and retry uses the same key and task', async () => {
  const request = jest.fn<Request>().mockResolvedValueOnce(details).mockRejectedValueOnce(new ApiError(0))
    .mockResolvedValue({ ...done, task_completed: true });
  await render(<Completion id={42} taskId={7} reflectionOnly={false} request={request} owner={null} />);
  await press('Отметить изученным');
  expect(screen.queryByText(/Материал изучен/)).toBeNull();
  expect(screen.getByText('Для сохранения на сервере нужно подключение.')).toBeTruthy();
  await press('Отметить изученным');
  expect(request.mock.calls[2]).toEqual(request.mock.calls[1]);
  expect(request.mock.calls[1]).toEqual([`${path}/completion`, 'POST', { task_id: 7 }, { version: 3, idempotencyKey: expect.any(String) }]);
  expect(screen.getByRole('header', { name: 'Материал изучен' })).toBeTruthy();
  expect(screen.getByText('Задание завершено.')).toBeTruthy();
  await press('Создать вопрос для повторения');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/review', params: { id: '42' } });
  await press('Готово');
  expect(router.back).toHaveBeenCalled();
  expect(request.mock.calls.filter(call => call[0].endsWith('/reflection'))).toHaveLength(0);
});

test('by default leaves the active task open and optionally saves a thought', async () => {
  const request = jest.fn<Request>().mockResolvedValueOnce(details).mockResolvedValueOnce(done)
    .mockResolvedValue({ thought: 'Идея', version: 1 });
  await render(<Completion id={42} taskId={null} reflectionOnly={false} request={request} owner={null} />);
  expect(screen.getByRole('button', { name: 'Также завершить задание · Только материал' })).toBeTruthy();
  await press('Отметить изученным');
  expect(request.mock.calls[1][2]).toEqual({ task_id: null });
  expect(screen.queryByLabelText('Главная мысль (необязательно)')).toBeNull();
  await press('Главная мысль (необязательно)');
  await fireEvent.changeText(screen.getByLabelText('Главная мысль (необязательно)'), 'Идея');
  await press('Сохранить главную мысль');
  expect(request).toHaveBeenCalledWith(`${path}/reflection`, 'PUT', { thought: 'Идея', previous: null });
  expect(screen.getByText('Главная мысль сохранена.')).toBeTruthy();
});

test('preserves the offline draft and only uploads after the user retries online', async () => {
  const owner = 'https://example.com/1';
  const request = jest.fn<Request>().mockRejectedValueOnce(new ApiError(0)).mockResolvedValue(details);
  jest.mocked(reflectionDraft).mockResolvedValue(null);
  jest.mocked(saveReflectionDraft).mockResolvedValue(undefined);
  await render(<Completion id={42} taskId={null} reflectionOnly request={request} owner={owner} />);
  await fireEvent.changeText(screen.getByLabelText('Главная мысль (необязательно)'), 'Локальная мысль');
  expect(saveReflectionDraft).toHaveBeenCalledWith(owner, 42, 'Локальная мысль', 1);
  expect(screen.getByText('Черновик сохранён на устройстве.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Сохранить главную мысль' }).props.accessibilityState.disabled).toBe(true);
  await press('Обновить');
  expect(screen.getByDisplayValue('Локальная мысль')).toBeTruthy();
  expect(request.mock.calls.filter(call => call[1] === 'PUT')).toHaveLength(0);
});

test('a successful external open prompts once after returning and a failed open never prompts', async () => {
  let change!: (state: AppStateStatus) => void;
  const events = jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') change = listener;
    return { remove: jest.fn() };
  });
  try {
    const view = await renderHook(() => useSourceReturn());
    await act(async () => { view.result.current.start()(false); change('background'); change('active'); });
    expect(view.result.current.prompt).toBe(false);
    await act(async () => { view.result.current.start()(true); });
    expect(view.result.current.prompt).toBe(false);
    await act(async () => { change('background'); change('active'); });
    expect(view.result.current.prompt).toBe(true);
    await act(async () => { view.result.current.dismiss(); change('background'); change('active'); });
    expect(view.result.current.prompt).toBe(false);
  } finally {
    events.mockRestore();
  }
});
