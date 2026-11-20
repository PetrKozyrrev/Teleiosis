import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import { openURL } from 'expo-linking';
import { enqueue } from '../src/offline/store';
import type { Material, MaterialPage, Request } from '../src/library/model';
import { useAuth } from '../src/auth/context';
import { ApiError } from '../src/auth/api';
import type { AuthController } from '../src/auth/controller';
import Library from '../src/app/(tabs)/index';
import MaterialRoute from '../src/app/library/[id]';

jest.mock('../src/offline/store', () => ({ enqueue: jest.fn(), subscribe: () => () => {}, ownerKey: () => 'account-1', unassigned: '' }));
jest.mock('../src/offline/cache', () => ({ readOnline: async (_owner: unknown, request: Request, path: Parameters<Request>[0]) => ({
  value: await request(path, 'GET'),
}), remember: async () => {}, forgetMaterial: async () => {} }));
jest.mock('../src/auth/config', () => ({ ...jest.requireActual<Record<string, unknown>>('../src/auth/config'), API_ORIGIN: 'https://example.com' }));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), replace: jest.fn() },
  useFocusEffect: (callback: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
  useLocalSearchParams: () => ({ id: mockRequestedId }),
  useNavigation: () => ({ isFocused: () => true }),
}));
jest.mock('expo-linking', () => ({ openURL: jest.fn() }));

const request = jest.fn<Request>();
const item: Material = {
  id: 12, title: 'Тестовый PDF', url: 'https://example.com/sample.pdf', description: null, note: 'Пример',
  status: 'unseen', source: 'web', category_id: 3, open_count: 0, version: 1,
};
const user = { id: 1, email: 'test@example.com', timezone: 'UTC', reminders_enabled: false, reminder_time: '10:00', email_verified_at: null };
const page = (items: Material[], total = items.length, offset = 0): MaterialPage => ({ items, total, limit: 20, offset });
let mockRequestedId: string;

function press(name: string) {
  return fireEvent.press(screen.getByRole('button', { name }));
}

beforeEach(() => {
  mockRequestedId = 'new';
  jest.mocked(enqueue).mockReset().mockResolvedValue(undefined);
  request.mockReset().mockImplementation(async path => path === '/categories' ? [{ id: 3, name: 'Техника', contents_count: 1 }] : item);
  jest.mocked(router.replace).mockClear();
  jest.mocked(router.push).mockClear();
  jest.mocked(openURL).mockReset().mockResolvedValue(true);
  jest.mocked(useAuth).mockReturnValue({
    controller: { library: request, captureSession: () => () => true } as unknown as AuthController,
    state: { phase: 'signedIn', session: { user, expires_at: '', absolute_expires_at: '' }, busy: false, message: null },
  });
});

test('opens category management from the library with filters closed', async () => {
  request.mockImplementation(async path => path === '/categories' ? [] : page([]));
  await render(<Library />);

  expect(screen.queryByRole('button', { name: 'Категория · Все категории' })).toBeNull();
  await press('Управлять категориями');
  expect(router.push).toHaveBeenCalledWith('/library/categories');

  await press('Фильтры и сортировка');
  expect(screen.getByRole('button', { name: 'Категория · Все категории' })).toBeTruthy();
  expect(screen.getAllByRole('button', { name: 'Управлять категориями' })).toHaveLength(1);
});

test('saves a PDF link in the local queue with its category', async () => {
  await render(<MaterialRoute />);
  await fireEvent.changeText(screen.getByLabelText('Ссылка'), item.url!);
  await press('Категория · Без категории');
  await fireEvent.press(screen.getByRole('radio', { name: 'Техника' }));
  await press('Сохранить');
  expect(enqueue).toHaveBeenCalledWith('account-1', { url: item.url!, category_id: 3 }, undefined);
  expect(router.replace).toHaveBeenCalledWith('/queue');
});

test('edits only changed fields, displays fallback and hands the original to the OS', async () => {
  mockRequestedId = '12';
  await render(<MaterialRoute />);
  expect(screen.getByText('Описание страницы недоступно.')).toBeTruthy();
  expect(screen.queryByLabelText('Дата и время напоминания')).toBeNull();
  await press('Редактировать');
  await fireEvent.changeText(screen.getByLabelText('Название'), 'Новое название');
  await press('Статус · Не просмотрено');
  await fireEvent.press(screen.getByRole('radio', { name: 'Изучено' }));
  await press('Сохранить');
  expect(request).toHaveBeenCalledWith('/contents/12/versioned', 'PATCH', { title: 'Новое название', status: 'studied' }, { version: 1 });
  await press('Открыть оригинал');
  expect(request).toHaveBeenCalledWith('/contents/12/open', 'POST');
  expect(openURL).toHaveBeenCalledWith(item.url!);
});

test('preserves the user edit when the server detects a version conflict', async () => {
  requestedConflict();
  await render(<MaterialRoute />);
  await press('Редактировать');
  await fireEvent.changeText(screen.getByLabelText('Название'), 'Локальная правка');
  await press('Сохранить');
  expect(screen.getByText(/Материал уже обновлён на сервере/)).toBeTruthy();
  expect(screen.getByLabelText('Название').props.value).toBe('Локальная правка');
  await press('Загрузить актуальную версию');
  expect(screen.getByText(item.title)).toBeTruthy();
});

function requestedConflict() {
  mockRequestedId = '12';
  request.mockImplementation(async (path, method) => {
    if (method === 'PATCH') throw new ApiError(412);
    return path === '/categories' ? [] : item;
  });
}

test('retains the form if persisting a long note on the device fails', async () => {
  jest.mocked(enqueue).mockRejectedValueOnce(new Error('Локальное хранилище недоступно.'));
  await render(<MaterialRoute />);
  await press('Вид материала · Ссылка');
  await fireEvent.press(screen.getByRole('radio', { name: 'Заметка' }));
  const note = 'Я'.repeat(10_000);
  await fireEvent.changeText(screen.getByLabelText('Текст заметки'), note);
  await press('Сохранить');
  expect(enqueue).toHaveBeenCalledWith('account-1', { note, category_id: null }, undefined);
  expect(screen.getByLabelText('Текст заметки').props.value).toBe(note);
  expect(screen.getByText('Локальное хранилище недоступно.')).toBeTruthy();
  expect(router.replace).not.toHaveBeenCalled();
});

test('ignores older search replies and queries the next page of the current search', async () => {
  jest.useFakeTimers();
  try {
    let resolveOld!: (value: MaterialPage) => void;
    request.mockImplementation(async path => {
      if (path === '/categories') return [];
      if (path.includes('q=old')) return new Promise<MaterialPage>(resolve => { resolveOld = resolve; });
      if (path.includes('offset=20')) return page([{ ...item, title: 'Результат второй страницы' }], 21, 20);
      return page([item], 21);
    });
    await render(<Library />);
    const search = screen.getByLabelText('Поиск по названию');
    await fireEvent.changeText(search, 'old');
    await act(async () => { jest.advanceTimersByTime(250); });
    await fireEvent.changeText(search, 'new');
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(screen.getByText(item.title)).toBeTruthy();
    await act(async () => { resolveOld(page([{ ...item, title: 'Устаревший результат' }])); });
    expect(screen.queryByText('Устаревший результат')).toBeNull();
    await press('Следующая страница');
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(request).toHaveBeenLastCalledWith('/contents?sort=newest&limit=20&offset=20&q=new', 'GET');
    expect(screen.getByText('Результат второй страницы')).toBeTruthy();
  } finally {
    jest.useRealTimers();
  }
});
