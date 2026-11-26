import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import { router } from 'expo-router';
import { openURL } from 'expo-linking';
import { AppState, type AppStateStatus } from 'react-native';
import { enqueue, getJob, listJobs, retry, type Job } from '../src/offline/store';
import type { Material, MaterialPage, Request } from '../src/library/model';
import { useAuth } from '../src/auth/context';
import { ApiError } from '../src/auth/api';
import type { AuthController } from '../src/auth/controller';
import Library from '../src/app/(tabs)/library';
import AddLink from '../src/app/add-link';
import MaterialRoute from '../src/app/library/[id]';
import { pickPdf } from '../src/library/pdf';

jest.mock('../src/offline/store', () => ({
  enqueue: jest.fn(), getJob: jest.fn(), listJobs: jest.fn(), retry: jest.fn(), generation: () => 0,
  subscribe: () => () => {}, ownerKey: () => 'account-1', unassigned: '',
}));
jest.mock('../src/offline/cache', () => ({ readOnline: async (_owner: unknown, request: Request, path: Parameters<Request>[0]) => ({
  value: await request(path, 'GET'),
}), remember: async () => {}, forgetMaterial: async () => {} }));
jest.mock('../src/auth/config', () => ({ ...jest.requireActual<Record<string, unknown>>('../src/auth/config'), API_ORIGIN: 'https://example.com' }));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), replace: jest.fn(), navigate: jest.fn(), dismissTo: jest.fn() },
  useFocusEffect: (callback: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
  useLocalSearchParams: () => ({ id: mockRequestedId }),
  useNavigation: () => ({ isFocused: () => true }),
}));
jest.mock('expo-linking', () => ({ openURL: jest.fn() }));
jest.mock('expo-clipboard', () => ({ getStringAsync: async () => 'https://example.com/saved' }));
jest.mock('../src/library/pdf', () => ({
  ...jest.requireActual<typeof import('../src/library/pdf')>('../src/library/pdf'),
  pickPdf: jest.fn(),
}));

const request = jest.fn<Request>();
const item: Material = {
  id: 12, title: 'Тестовый PDF', url: 'https://example.com/sample.pdf', description: null, note: 'Пример',
  status: 'unseen', source: 'web', category_id: 3, open_count: 0, version: 1,
};
const user = { id: 1, email: 'test@example.com', timezone: 'UTC', reminders_enabled: false, reminder_time: '10:00', email_verified_at: null };
const page = (items: Material[], total = items.length, offset = 0): MaterialPage => ({ items, total, limit: 10, offset });
let mockRequestedId: string;

function press(name: string) {
  return fireEvent.press(screen.getByRole('button', { name }));
}

beforeEach(() => {
  mockRequestedId = 'new';
  jest.mocked(pickPdf).mockReset();
  jest.mocked(enqueue).mockReset().mockResolvedValue(undefined);
  jest.mocked(getJob).mockReset().mockResolvedValue(null);
  jest.mocked(listJobs).mockReset().mockResolvedValue([]);
  jest.mocked(retry).mockReset().mockResolvedValue(undefined);
  request.mockReset().mockImplementation(async path => path === '/categories' ? [{ id: 3, name: 'Техника', contents_count: 1 }] : item);
  jest.mocked(router.replace).mockClear();
  jest.mocked(router.push).mockClear();
  jest.mocked(router.navigate).mockClear();
  jest.mocked(router.dismissTo).mockClear();
  jest.mocked(openURL).mockReset().mockResolvedValue(true);
  jest.mocked(useAuth).mockReturnValue({
    controller: { library: request, captureSession: () => () => true, snapshot: () => ({ busy: false }) } as unknown as AuthController,
    state: { phase: 'signedIn', session: { user, expires_at: '', absolute_expires_at: '' }, busy: false, message: null },
  });
});

test('opens category management from the library with filters closed', async () => {
  request.mockImplementation(async path => path === '/categories' || path.startsWith('/mobile/library/') ? [] : page([]));
  await render(<Library />);

  expect(screen.queryByRole('button', { name: 'Категория · Все категории' })).toBeNull();
  await press('Управлять категориями');
  expect(router.push).toHaveBeenCalledWith('/library/categories');

  await press('Фильтры и сортировка');
  expect(screen.getByRole('button', { name: 'Категория · Все категории' })).toBeTruthy();
  expect(screen.getAllByRole('button', { name: 'Управлять категориями' })).toHaveLength(1);
});

test('shows only incoming drafts in the library and offers retry on Add Link', async () => {
  const job: Job = { id: 'unsent', owner: 'account-1', state: 'needs_action', payload: '{"note":"Неотправленный текст"}',
    reason: 'unavailable', server_id: null, attempts: 1, next_at: 0, tried_at: null };
  jest.mocked(listJobs).mockImplementation(async owner => owner ? [job, { ...job, id: 'waiting', state: 'pending' }, { ...job, id: 'saved', state: 'synced' }]
    : [{ ...job, id: 'incoming', owner: '', state: 'draft', reason: null, attempts: 0, payload: '{"note":"Из Поделиться"}' }]);
  request.mockImplementation(async path => path === '/categories' ? [] : page([]));
  const library = await render(<Library />);
  expect(screen.queryByRole('button', { name: 'Отправка и входящие' })).toBeNull();
  await press('Входящие материалы · 1');
  expect(screen.getByText('Из Поделиться')).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Неотправленные материалы|Ошибки отправки/ })).toBeNull();
  expect(listJobs).not.toHaveBeenCalledWith('account-1');
  await library.unmount();

  await render(<AddLink />);
  await press('Ошибки отправки · 1');
  await press('Повторить отправку');
  expect(retry).toHaveBeenCalledWith('account-1', 'unsent');
  expect(screen.queryByText('Сохранено на сервере')).toBeNull();
});

test('uses a user category as a quick filter', async () => {
  request.mockImplementation(async path => path === '/categories'
    ? [{ id: 3, name: 'Техника', contents_count: 1 }] : page([]));
  await render(<Library />);
  expect(screen.queryByRole('button', { name: 'Статьи' })).toBeNull();
  await press('Техника');
  await waitFor(() => expect(request.mock.calls.some(([path]) => path.startsWith('/contents?')
    && new URLSearchParams(path.split('?')[1]).get('category_id') === '3')).toBe(true));
});

test('shows a saved date, exact video length and approximate reading time on library cards', async () => {
  const materials = [
    { ...item, id: 1, title: 'Запись', content_type: 'video', video_duration_seconds: 750, created_at: '2026-11-25T12:00:00Z' },
    { ...item, id: 2, title: 'Статья', content_type: 'article', reading_minutes: 3 },
    { ...item, id: 3, title: 'Старый PDF', content_type: 'pdf', created_at: 'invalid', reading_minutes: null },
  ];
  request.mockImplementation(async path => path === '/categories' ? [] : page(materials));
  await render(<Library />);

  expect(await screen.findByText('12 мин 30 с')).toBeTruthy();
  expect(screen.getByText(/^Добавлено /)).toBeTruthy();
  expect(screen.getByText('≈ 3 мин чтения')).toBeTruthy();
  expect(screen.queryByText(/invalid/i)).toBeNull();
});

test('pastes a link, persists the selected collection and confirms saving on the same tab', async () => {
  request.mockResolvedValue([{ id: 8, name: 'На выходные', contents_count: 0 }]);
  jest.mocked(enqueue).mockResolvedValue('new-job');
  await render(<AddLink />);
  expect(screen.getByRole('button', { name: 'Сохранить в библиотеку' }).props.accessibilityState.disabled).toBe(true);
  await press('Вставить');
  expect(screen.getByLabelText('Ссылка').props.value).toBe('https://example.com/saved');
  await press('Добавить в подборку');
  await press('Коллекции · Не выбраны');
  await fireEvent.press(screen.getByRole('checkbox', { name: 'На выходные' }));
  await press('Сохранить в библиотеку');
  expect(enqueue).toHaveBeenCalledWith('account-1', { url: 'https://example.com/saved', collection_ids: [8] });
  expect(router.push).not.toHaveBeenCalledWith('/queue');
  expect(screen.getByText('Ссылка сохранена на устройстве и появится в библиотеке после отправки.')).toBeTruthy();
  await press('Открыть библиотеку');
  expect(router.navigate).toHaveBeenCalledWith('/library');
});

test('dismisses confirmation five seconds after syncing or when opening the library', async () => {
  jest.useFakeTimers();
  const success = 'Ссылка добавлена в библиотеку.';
  jest.mocked(enqueue).mockResolvedValueOnce('first-job').mockResolvedValueOnce('second-job');
  const syncedJob: Job = { id: 'first-job', owner: 'account-1', state: 'synced', payload: '{}', reason: null,
    server_id: 12, attempts: 1, next_at: 0, tried_at: 1 };
  jest.mocked(getJob).mockResolvedValueOnce(syncedJob).mockResolvedValueOnce({ ...syncedJob, id: 'second-job' });
  try {
    await render(<AddLink />);
    await press('Вставить');
    await press('Сохранить в библиотеку');
    await act(() => jest.advanceTimersByTime(4_999));
    expect(screen.getByText(success)).toBeTruthy();
    await act(() => jest.advanceTimersByTime(1));
    expect(screen.queryByText(success)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Открыть библиотеку' })).toBeNull();

    await press('Вставить');
    await press('Сохранить в библиотеку');
    expect(screen.getByText(success)).toBeTruthy();
    await press('Открыть библиотеку');
    expect(router.navigate).toHaveBeenCalledWith('/library');
    expect(screen.queryByText(success)).toBeNull();
  } finally {
    jest.useRealTimers();
  }
});

test('saves a PDF link in the local queue with its category', async () => {
  await render(<MaterialRoute />);
  await fireEvent.changeText(screen.getByLabelText('Ссылка'), item.url!);
  await press('Категория · Без категории');
  await fireEvent.press(screen.getByRole('radio', { name: 'Техника' }));
  await press('Сохранить');
  expect(enqueue).toHaveBeenCalledWith('account-1', { url: item.url!, category_id: 3 }, undefined);
  expect(router.dismissTo).toHaveBeenCalledWith('/library');
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

test('dismisses the return prompt without changing the material status', async () => {
  mockRequestedId = '12';
  let change!: (state: AppStateStatus) => void;
  const previous = jest.isMockFunction(AppState.addEventListener)
    ? jest.mocked(AppState.addEventListener).getMockImplementation() : undefined;
  const events = jest.spyOn(AppState, 'addEventListener').mockImplementation((event, listener) => {
    if (event === 'change') change = listener;
    return { remove: jest.fn() };
  });
  try {
    await render(<MaterialRoute />);
    await press('Открыть оригинал');
    expect(screen.queryByText('Удалось изучить?')).toBeNull();
    await act(async () => { change('background'); change('active'); });
    expect(screen.getByRole('header', { name: 'Удалось изучить?' })).toBeTruthy();
    await press('Не сейчас');
    expect(screen.queryByText('Удалось изучить?')).toBeNull();
    expect(screen.getByText('Не просмотрено')).toBeTruthy();
    expect(request.mock.calls.filter(([, method]) => method !== 'GET')).toEqual([['/contents/12/open', 'POST']]);
    await press('Отметить изученным');
    expect(router.push).toHaveBeenCalledWith({ pathname: '/library/complete', params: { id: '12' } });
  } finally {
    if (previous) events.mockImplementation(previous);
    else events.mockRestore();
  }
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
    const materials = Array.from({ length: 18 }, (_, index) => ({ ...item, id: index + 20, title: `Материал ${index + 1}` }));
    request.mockImplementation(async path => {
      if (path === '/categories') return [];
      if (path.includes('q=old')) return new Promise<MaterialPage>(resolve => { resolveOld = resolve; });
      if (path.includes('offset=10')) return page(materials.slice(10), 18, 10);
      return page(materials.slice(0, 10), 18);
    });
    await render(<Library />);
    const search = screen.getByLabelText('Поиск по названию');
    await fireEvent.changeText(search, 'old');
    await act(async () => { jest.advanceTimersByTime(250); });
    await fireEvent.changeText(search, 'new');
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(screen.getByText('Сначала новые')).toBeTruthy();
    expect(screen.queryByText('Сортировка · Сначала новые')).toBeNull();
    expect(screen.getAllByText(/^Материал \d+$/)).toHaveLength(10);
    expect(screen.queryByText('Материал 11')).toBeNull();
    await act(async () => { resolveOld(page([{ ...item, title: 'Устаревший результат' }])); });
    expect(screen.queryByText('Устаревший результат')).toBeNull();
    await press('Показать больше');
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(request).toHaveBeenLastCalledWith('/contents?sort=newest&limit=10&offset=10&q=new', 'GET');
    expect(screen.getAllByText(/^Материал \d+$/)).toHaveLength(18);
    expect(screen.getByText('Материал 1')).toBeTruthy();
    expect(screen.getByText('Материал 18')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Показать больше' })).toBeNull();
    request.mockClear();
    await press('Скрыть лишнее');
    expect(screen.getAllByText(/^Материал \d+$/)).toHaveLength(10);
    expect(screen.queryByRole('button', { name: 'Скрыть лишнее' })).toBeNull();
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(request).not.toHaveBeenCalled();
    await press('Показать больше');
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(request).toHaveBeenLastCalledWith('/contents?sort=newest&limit=10&offset=10&q=new', 'GET');
    expect(screen.getAllByText(/^Материал \d+$/)).toHaveLength(18);
    await press('Сортировка · Сначала новые');
    await fireEvent.press(screen.getByRole('radio', { name: 'Сначала старые' }));
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(request).toHaveBeenLastCalledWith('/contents?sort=oldest&limit=10&offset=0&q=new', 'GET');
    expect(screen.getByText('Сначала старые')).toBeTruthy();
    expect(screen.getAllByText(/^Материал \d+$/)).toHaveLength(10);
  } finally {
    jest.useRealTimers();
  }
});

test('retains the visible materials when loading more fails and retries the same offset', async () => {
  const morePath = '/contents?sort=newest&limit=10&offset=10';
  let attempts = 0;
  request.mockImplementation(async path => {
    if (path === '/categories') return [];
    if (path === morePath) {
      if (++attempts === 1) throw new ApiError(0);
      return page([{ ...item, id: 13, title: 'Следующий материал' }], 11, 10);
    }
    return page([item], 11);
  });
  await render(<Library />);
  await fireEvent.press(await screen.findByRole('button', { name: 'Показать больше' }));
  await fireEvent.press(await screen.findByRole('button', { name: 'Повторить загрузку' }));
  expect(screen.getByText(item.title)).toBeTruthy();
  expect(await screen.findByText('Следующий материал')).toBeTruthy();
  expect(request.mock.calls.filter(([path]) => path === morePath)).toHaveLength(2);
});


test('offers organization outside filters and combines tag and collection filters', async () => {
  request.mockImplementation(async path => path === '/mobile/library/tags' ? [{ id: 9, name: 'Метка', contents_count: 0 }]
    : path === '/mobile/library/collections' ? [{ id: 10, name: 'Подборка', contents_count: 0 }]
      : path === '/categories' ? [] : page([]));
  await render(<Library />);
  await press('Теги и коллекции');
  expect(router.push).toHaveBeenCalledWith('/library/organization');
  await press('Фильтры и сортировка');
  await press('Фильтры по тегам и коллекциям');
  await press('Тег · Все теги');
  await fireEvent.press(screen.getByRole('radio', { name: 'Метка' }));
  await press('Коллекция · Все коллекции');
  await fireEvent.press(screen.getByRole('radio', { name: 'Подборка' }));
  await waitFor(() => expect(request.mock.calls.some(([path]) => path.startsWith('/contents?')
    && new URLSearchParams(path.split('?')[1]).get('tag_id') === '9'
    && new URLSearchParams(path.split('?')[1]).get('collection_id') === '10')).toBe(true));
});

test('advanced search resets pagination, ignores stale results and requires a connection', async () => {
  jest.useFakeTimers();
  try {
    let resolveOld!: (value: MaterialPage) => void;
    request.mockImplementation(async path => {
      if (path === '/categories' || path === '/mobile/library/tags' || path === '/mobile/library/collections') return [];
      if (path.includes('search_in=note')) return new Promise<MaterialPage>(resolve => { resolveOld = resolve; });
      if (path.includes('search_in=url')) throw new ApiError(0);
      return path.includes('offset=10') ? page([{ ...item, id: 13 }], 21, 10) : page([item], 21);
    });
    await render(<Library />);
    await fireEvent.changeText(screen.getByLabelText('Поиск по названию'), 'текст');
    await act(async () => { jest.advanceTimersByTime(250); });
    await press('Показать больше');
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(request).toHaveBeenLastCalledWith(expect.stringContaining('offset=10'), 'GET');
    await press('Фильтры и сортировка');
    await press('Искать в · Название · доступно офлайн');
    await fireEvent.press(screen.getByRole('radio', { name: 'Заметка' }));
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(request).toHaveBeenLastCalledWith(expect.stringMatching(/^\/mobile\/library\/search\?.*offset=0.*search_in=note$/), 'GET');
    await press('Искать в · Заметка');
    await fireEvent.press(screen.getByRole('radio', { name: 'Ссылка' }));
    await act(async () => { jest.advanceTimersByTime(250); });
    expect(screen.getByText('Расширенный поиск доступен при подключении к серверу.')).toBeTruthy();
    await act(async () => { resolveOld(page([{ ...item, title: 'Устаревший ответ по заметке' }])); });
    expect(screen.queryByText('Устаревший ответ по заметке')).toBeNull();
    expect(screen.queryByText(item.title)).toBeNull();
  } finally {
    jest.useRealTimers();
  }
});

test('creates a standalone PDF from the new material form and retries after an unknown result', async () => {
  const bytes = new Uint8Array([37, 80, 68, 70]).buffer;
  jest.mocked(pickPdf).mockResolvedValueOnce({ name: 'document.pdf', bytes });
  const create = '/mobile/library/pdf?category_id=3';
  let attempts = 0;
  request.mockImplementation(async path => {
    if (path === '/categories') return [{ id: 3, name: 'Техника', contents_count: 1 }];
    if (path === create && ++attempts === 1) throw new ApiError(0);
    return { id: 12 };
  });
  await render(<MaterialRoute />);
  await press('Вид материала · Ссылка');
  await fireEvent.press(screen.getByRole('radio', { name: 'PDF' }));
  await press('Выбрать PDF');
  expect(request).toHaveBeenLastCalledWith('/mobile/library/pdf', 'GET');
  expect(screen.getByText('document.pdf')).toBeTruthy();
  await press('Категория · Без категории');
  await fireEvent.press(screen.getByRole('radio', { name: 'Техника' }));
  await fireEvent.changeText(screen.getByLabelText('Название (необязательно)'), 'Справочник');
  await press('Сохранить');
  expect(screen.getByText('Для работы с PDF требуется подключение к серверу.')).toBeTruthy();
  await press('Сохранить');
  expect(request.mock.calls.filter(([path]) => path === create)).toEqual([
    [create, 'POST', bytes, { pdfFilename: 'document.pdf', pdfTitle: 'Справочник' }],
    [create, 'POST', bytes, { pdfFilename: 'document.pdf', pdfTitle: 'Справочник' }],
  ]);
  expect(enqueue).not.toHaveBeenCalled();
  expect(router.replace).toHaveBeenCalledWith({ pathname: '/library/[id]', params: { id: '12' } });
});

test('explains that the old staging API lacks PDF creation before opening the file picker', async () => {
  request.mockImplementation(async path => {
    if (path === '/mobile/library/pdf') throw new ApiError(404);
    return [];
  });
  await render(<MaterialRoute />);
  await press('Вид материала · Ссылка');
  await fireEvent.press(screen.getByRole('radio', { name: 'PDF' }));
  await press('Выбрать PDF');
  expect(screen.getByText('Сервер пока не поддерживает создание PDF-материалов.')).toBeTruthy();
  expect(pickPdf).not.toHaveBeenCalled();
});
