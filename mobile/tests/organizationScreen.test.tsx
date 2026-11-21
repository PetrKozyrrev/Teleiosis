import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { beforeEach, expect, jest, test } from '@jest/globals';
import { ApiError } from '../src/auth/api';
import type { Request } from '../src/library/model';
import type { Organization } from '../src/library/organization';
import OrganizationRoute from '../src/app/library/organization';
import OrganizeRoute from '../src/app/library/organize';
import { GroupSelection } from '../src/library/GroupSelection';

jest.mock('../src/offline/store', () => ({ ownerKey: () => 'synthetic-owner' }));
jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));

jest.mock('../src/library/ui', () => ({
  ...jest.requireActual<typeof import('../src/library/ui')>('../src/library/ui'),
  LibraryAccess: ({ children }: { children: (request: Request) => React.ReactNode }) => children(mockRequest),
}));
jest.mock('expo-router', () => ({
  router: { push: jest.fn() }, useLocalSearchParams: () => ({ id: '12' }),
  useFocusEffect: (callback: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
}));
const mockRequest = jest.fn<Request>();
const tag = { id: 3, name: 'Техника', contents_count: 0 };
const collection = { id: 4, name: 'На выходные', contents_count: 1 };
const empty: Organization = { content_id: 12, version: 7, tags: [], collections: [collection] };
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
beforeEach(() => {
  mockRequest.mockReset().mockImplementation(async path => path.endsWith('/organization') ? empty
    : path === '/mobile/library/tags' ? [tag] : [collection]);
});

test('creates and renames tags, with one POST when the response is lost', async () => {
  await render(<OrganizationRoute />);
  await fireEvent.changeText(screen.getByLabelText('Название тега'), '  Пример  ');
  mockRequest.mockRejectedValueOnce(new ApiError(0));
  await press('Создать тег');
  expect(mockRequest).toHaveBeenCalledWith('/mobile/library/tags', 'POST', { name: 'Пример' });
  expect(mockRequest.mock.calls.filter(call => call[1] === 'POST')).toHaveLength(1);
  expect(screen.getByText('Ответ не получен. Обновите список перед повтором: запись могла сохраниться.')).toBeTruthy();
  await press('Обновить теги и коллекции');
  await press('Переименовать «Техника»');
  await fireEvent.changeText(screen.getByLabelText('Название тега'), 'Обновлено');
  await press('Сохранить название');
  expect(mockRequest).toHaveBeenCalledWith('/mobile/library/tags/3', 'PATCH', { name: 'Обновлено' });
});

test('does not show a late tag response after switching to collections', async () => {
  let resolve!: (value: unknown) => void;
  mockRequest.mockImplementation(async path => path === '/mobile/library/tags' ? new Promise(done => { resolve = done; }) : [collection]);
  await render(<OrganizationRoute />);
  await press('Раздел · Теги');
  await fireEvent.press(screen.getByRole('radio', { name: 'Коллекции' }));
  await act(async () => { resolve([tag]); });
  expect(screen.getByLabelText('Название коллекции')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Переименовать «Техника»' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Переименовать «На выходные»' })).toBeTruthy();
});

test('distinguishes quota errors and an old server', async () => {
  await render(<OrganizationRoute />);
  await fireEvent.changeText(screen.getByLabelText('Название тега'), 'Пример');
  mockRequest.mockRejectedValueOnce(new ApiError(409, false, null, null, 'group_limit_reached'));
  await press('Создать тег');
  expect(screen.getByText(/Достигнут лимит/)).toBeTruthy();
  mockRequest.mockRejectedValueOnce(new ApiError(404));
  await press('Обновить теги и коллекции');
  expect(screen.getByText(/Требуется обновление сервера/)).toBeTruthy();
});

test('assigns multiple groups with the current version while preserving the other kind', async () => {
  await render(<OrganizeRoute />);
  await press('Теги · Не выбраны');
  await fireEvent.press(screen.getByRole('checkbox', { name: 'Техника' }));
  mockRequest.mockResolvedValueOnce({ ...empty, version: 8, tags: [tag] });
  await press('Сохранить теги и коллекции');
  expect(mockRequest).toHaveBeenLastCalledWith('/mobile/library/contents/12/organization', 'PATCH',
    { tag_ids: [3], collection_ids: [4] }, { version: 7 });
  expect(screen.getByText('Теги и коллекции сохранены.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Сохранить теги и коллекции' }).props.accessibilityState.disabled).toBe(true);
});

test.each([412, 0])('keeps selection on %s and requires an explicit reload before another write', async status => {
  await render(<OrganizeRoute />);
  await press('Теги · Не выбраны');
  await fireEvent.press(screen.getByRole('checkbox', { name: 'Техника' }));
  mockRequest.mockRejectedValueOnce(new ApiError(status));
  await press('Сохранить теги и коллекции');
  expect(screen.getByRole('checkbox', { name: 'Техника' }).props.accessibilityState.checked).toBe(true);
  expect(screen.getByRole('button', { name: 'Сохранить теги и коллекции' }).props.accessibilityState.disabled).toBe(true);
  expect(mockRequest.mock.calls.filter(call => call[1] === 'PATCH')).toHaveLength(1);
  await press('Загрузить актуальные теги и коллекции');
  expect(screen.getByRole('button', { name: 'Теги · Не выбраны' })).toBeTruthy();
});


test('limits a material selection to 20 without discarding the current selection', async () => {
  const onChange = jest.fn<(value: number[]) => void>();
  const items = Array.from({ length: 21 }, (_, id) => ({ id: id + 1, name: `Synthetic ${id + 1}`, contents_count: 0 }));
  await render(<GroupSelection label="Теги" items={items} selected={items.slice(0, 20).map(item => item.id)} onChange={onChange} disabled={false} />);
  await fireEvent.press(screen.getByRole('button'));
  await fireEvent.press(screen.getByRole('checkbox', { name: 'Synthetic 21' }));
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByText('Можно выбрать не более 20.')).toBeTruthy();
});
