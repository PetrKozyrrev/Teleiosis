import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import { Alert } from 'react-native';
import { ApiError } from '../src/auth/api';
import { GoalDetail, GoalPicker, GoalsList } from '../src/learning/goals';
import type { Request } from '../src/library/model';
import { forgetGoalRecommendations } from '../src/offline/cache';

jest.mock('../src/offline/cache', () => ({
  forgetGoalRecommendations: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
}));

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), navigate: jest.fn(), back: jest.fn(), canGoBack: () => true, replace: jest.fn() },
  useFocusEffect: (callback: () => void) =>
    jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
}));

const path = '/mobile/learning/goals';
const goal = { id: 42, name: 'Освоить Python', result: null, status: 'active', version: 1,
  materials_total: 0, materials_studied: 0 };
const material = { id: 12, title: 'Курс Python', status: 'unseen' };
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
async function confirm(name: string) {
  const alert = jest.spyOn(Alert, 'alert').mockImplementation((_title, _message, actions) => {
    actions?.find(action => action.text === name)?.onPress?.();
  });
  try {
    await press(name);
  } finally {
    alert.mockRestore();
  }
}

test('creates a goal without a deadline, progress target, or required description', async () => {
  const request = jest.fn<Request>().mockResolvedValueOnce({ items: [], total: 0 }).mockResolvedValueOnce(goal)
    .mockResolvedValue({ items: [goal], total: 1 });
  await render(<GoalsList request={request} />);
  await press('Создать цель');
  await fireEvent.changeText(screen.getByLabelText('Название цели'), ' Освоить Python ');
  await press('Создать цель');
  expect(request).toHaveBeenCalledWith(path, 'POST', { name: 'Освоить Python', result: null });
  expect(router.push).toHaveBeenCalledWith({ pathname: '/goals/[id]', params: { id: '42' } });
});

test('links one material to two goals and allows an independent unlink', async () => {
  const linked = new Set<number>();
  const request = jest.fn<Request>().mockImplementation(async (url, method) => {
    if (method === 'POST') linked.add(url.includes('/42/') ? 42 : 43);
    if (method === 'DELETE') linked.delete(42);
    return { items: [goal, { ...goal, id: 43, name: 'Вторая цель' }].map(row => ({ ...row, linked: linked.has(row.id) })), total: 2 };
  });
  await render(<GoalsList request={request} contentId={12} />);
  await fireEvent.press(screen.getAllByRole('button', { name: 'Привязать материал' })[0]);
  await press('Привязать материал');
  expect(screen.getAllByText('Материал уже связан с целью.')).toHaveLength(2);
  await fireEvent.press(screen.getAllByRole('button', { name: 'Отвязать материал' })[0]);
  expect(request).toHaveBeenCalledWith(`${path}/42/materials/12`, 'DELETE');
  expect(screen.getAllByText('Материал уже связан с целью.')).toHaveLength(1);
});

test('opens the material picker and schedules, edits, completes and archives the goal', async () => {
  let current = { ...goal };
  const request = jest.fn<Request>().mockImplementation(async (url, method, body) => {
    if (method === 'PUT') {
      current = { ...current, ...(body as typeof goal), version: current.version + 1 };
      return current;
    }
    if (url.startsWith(`${path}/42/materials?`)) {
      return { items: [material], total: 1 };
    }
    return current;
  });
  await render(<GoalDetail request={request} id={42} />);
  expect(screen.queryByText('Добавьте материалы')).toBeNull();
  await press('Добавить из библиотеки');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/goals/materials', params: { goalId: '42' } });
  await press('Запланировать материал');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/plan', params: { id: '12', goalId: '42' } });
  await press('Редактировать цель');
  await fireEvent.changeText(screen.getByLabelText('Желаемый результат (необязательно)'), 'Написать программу');
  await press('Сохранить цель');
  expect(request).toHaveBeenCalledWith(`${path}/42`, 'PUT', {
    name: goal.name, result: 'Написать программу', status: 'active',
  }, { version: 1 });
  await confirm('Завершить цель');
  expect(screen.getByText('Завершённая цель')).toBeTruthy();
  await confirm('Архивировать цель');
  expect(screen.getByText('Архивная цель')).toBeTruthy();
  expect(screen.getByText(/Курс Python ·/)).toBeTruthy();
});

test('shows the desired result separately from the empty material section and opens the picker', async () => {
  const request = jest.fn<Request>().mockImplementation(async url => url.includes('/materials?')
    ? { items: [], total: 0 } : { ...goal, result: 'Решить пять задач' });
  await render(<GoalDetail request={request} id={42} />);
  expect(screen.getByRole('header', { name: 'Желаемый результат' })).toBeTruthy();
  expect(screen.getByText('Решить пять задач')).toBeTruthy();
  expect(screen.queryByText('Добавьте материалы')).toBeNull();
  await press('Добавить материалы');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/goals/materials', params: { goalId: '42' } });
});

test('permanently removes an archived goal only after confirmation and refreshes its learning snapshots', async () => {
  const request = jest.fn<Request>().mockImplementation(async (url, method) => {
    if (method === 'DELETE') return;
    return url.includes('/materials?') ? { items: [], total: 0 } : { ...goal, status: 'archived', version: 3 };
  });
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  try {
    await render(<GoalDetail request={request} id={42} owner="https://example.com/1" />);
    await press('Удалить цель');
    expect(request.mock.calls.some(([, method]) => method === 'DELETE')).toBe(false);
    expect(alert.mock.calls[0][1]).toContain('Материалы останутся в библиотеке.');
    await act(() => alert.mock.calls[0][2]?.find(button => button.style === 'destructive')?.onPress?.());
    expect(request).toHaveBeenCalledWith(`${path}/42`, 'DELETE', undefined, { version: 3 });
    expect(forgetGoalRecommendations).toHaveBeenCalledWith('https://example.com/1');
    expect(router.back).toHaveBeenCalled();
  } finally {
    alert.mockRestore();
  }
});

test('keeps the goal visible and explains the missing DELETE on an older server', async () => {
  const request = jest.fn<Request>().mockImplementation(async (url, method) => {
    if (method === 'DELETE') throw new ApiError(405);
    return url.includes('/materials?') ? { items: [], total: 0 } : goal;
  });
  await render(<GoalDetail request={request} id={42} />);
  await confirm('Удалить цель');
  expect(screen.getByText('Для удаления целей требуется обновление сервера.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Удалить цель' })).toBeTruthy();
  expect(router.back).not.toHaveBeenCalled();
});

test('selects across pages, skips linked materials and retries only unconfirmed writes', async () => {
  const first = { ...material, content_type: 'video', duration_minutes: 5, linked: false };
  const already = { ...first, id: 13, title: 'Уже связан', linked: true };
  const second = { ...first, id: 14, title: 'Практика Python', duration_minutes: null };
  let attempts = 0;
  const request = jest.fn<Request>().mockImplementation(async (url, method, body) => {
    if (method === 'POST') {
      if ((body as { content_id: number }).content_id === 14 && attempts++ === 0) throw new ApiError(502);
      return;
    }
    return { items: url.includes('offset=0') ? [first, already] : [second], total: 101 };
  });
  await render(<GoalPicker request={request} id={42} />);
  const check = (name: RegExp) => screen.getByRole('checkbox', { name });
  expect(check(/Уже связан/).props.accessibilityState).toMatchObject({ checked: true, disabled: true });
  await fireEvent.press(check(/Курс Python/));
  await press('Следующая страница');
  await fireEvent.press(check(/Практика Python/));
  expect(screen.getByText('Выбрано: 2')).toBeTruthy();
  await press('Добавить выбранные');
  expect(screen.getByText('Добавлено: 1. Осталось добавить: 1.')).toBeTruthy();
  await press('Повторить добавление');
  expect(screen.getByText('Добавлено: 1. Осталось добавить: 0.')).toBeTruthy();
  expect(request.mock.calls.filter(call => call[1] === 'POST')).toEqual([12, 14, 14].map(content_id =>
    [`${path}/42/materials`, 'POST', { content_id }]));
  await press('Готово');
  expect(router.back).toHaveBeenCalled();
});
