import { fireEvent, render, screen } from '@testing-library/react-native';
import { expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import { GoalDetail, GoalsList } from '../src/learning/goals';
import type { Request } from '../src/library/model';

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), navigate: jest.fn() },
  useFocusEffect: (callback: () => void) =>
    jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
}));

const path = '/mobile/learning/goals';
const goal = { id: 42, name: 'Освоить Python', result: null, status: 'active', version: 1,
  materials_total: 0, materials_studied: 0 };
const material = { id: 12, title: 'Курс Python', status: 'unseen' };
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));

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

test('adds a library material, schedules through the existing plan, edits, completes and archives', async () => {
  let current = { ...goal };
  let linked = false;
  const request = jest.fn<Request>().mockImplementation(async (url, method, body) => {
    if (method === 'PUT') {
      current = { ...current, ...(body as typeof goal), version: current.version + 1 };
      return current;
    }
    if (method === 'POST') linked = true;
    if (url.startsWith('/contents?') || url.startsWith(`${path}/42/materials?`)) {
      const items = linked || url.startsWith('/contents?') ? [material] : [];
      return { items, total: items.length };
    }
    return current;
  });
  await render(<GoalDetail request={request} id={42} />);
  expect(screen.getByText('Добавьте материалы')).toBeTruthy();
  await press('Добавить из библиотеки');
  await press('Курс Python');
  expect(request).toHaveBeenCalledWith(`${path}/42/materials`, 'POST', { content_id: 12 });
  await press('Запланировать материал');
  expect(router.push).toHaveBeenCalledWith({ pathname: '/plan', params: { id: '12', goalId: '42' } });
  await press('Редактировать цель');
  await fireEvent.changeText(screen.getByLabelText('Желаемый результат (необязательно)'), 'Написать программу');
  await press('Сохранить цель');
  expect(request).toHaveBeenCalledWith(`${path}/42`, 'PUT', {
    name: goal.name, result: 'Написать программу', status: 'active',
  }, { version: 1 });
  await press('Завершить цель');
  expect(screen.getByText('Завершённая цель')).toBeTruthy();
  await press('Архивировать цель');
  expect(screen.getByText('Архивная цель')).toBeTruthy();
  expect(screen.getByText(/Курс Python ·/)).toBeTruthy();
});
