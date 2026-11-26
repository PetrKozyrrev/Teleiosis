import { beforeEach, expect, jest, test } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { AppState, Platform, type AppStateStatus } from 'react-native';
import { router } from 'expo-router';
import { clearSharedPayloads, getSharedPayloads } from 'expo-sharing';
import IncomingShare from '../src/app/share-probe';
import { assignDraft, importDraft, listJobs, type Job } from '../src/offline/store';

jest.mock('expo-router', () => ({
  router: { replace: jest.fn() },
  useFocusEffect: (callback: () => void) => jest.requireActual<typeof import('react')>('react').useEffect(callback, [callback]),
}));
jest.mock('expo-sharing', () => ({ getSharedPayloads: jest.fn(), clearSharedPayloads: jest.fn() }));
jest.mock('../src/offline/store', () => ({
  importDraft: jest.fn(), listJobs: jest.fn(), assignDraft: jest.fn(), ownerKey: () => 'account-1', unassigned: '',
  subscribe: (callback: () => void) => { mockNotify = callback; return () => { mockNotify = () => {}; }; },
}));
jest.mock('../src/auth/config', () => ({ ...jest.requireActual<Record<string, unknown>>('../src/auth/config'), API_ORIGIN: 'https://example.com' }));
jest.mock('../src/auth/context', () => ({
  useAuth: () => ({ controller: { snapshot: () => auth, captureSession: () => () => true }, state: auth }),
}));

const auth = { phase: 'signedIn', busy: false, session: { user: { id: 1, email: 'test@example.com' } } };
let mockNotify = () => {};

beforeEach(() => {
  Platform.OS = 'android';
  jest.mocked(listJobs).mockReset().mockResolvedValue([]);
  jest.mocked(assignDraft).mockReset().mockResolvedValue(undefined);
  jest.mocked(importDraft).mockReset().mockImplementation(async payload => {
    const draft: Job = { id: 'incoming-1', owner: '', state: 'draft', payload: JSON.stringify(payload),
      reason: null, server_id: null, attempts: 0, next_at: 0, tried_at: null };
    jest.mocked(listJobs).mockResolvedValue([draft]);
    mockNotify();
  });
  jest.mocked(clearSharedPayloads).mockReset().mockImplementation(() => { jest.mocked(getSharedPayloads).mockReturnValue([]); });
  jest.mocked(getSharedPayloads).mockReset().mockReturnValue([{ shareType: 'text', value: 'Проверочный текст' }]);
  jest.mocked(router.replace).mockClear();
});

test('persists the share as a draft before clearing the native payload', async () => {
  await render(<IncomingShare />);
  expect(screen.getByText('Проверочный текст')).toBeTruthy();
  expect(importDraft).toHaveBeenCalledWith({ note: 'Проверочный текст' });
  expect(jest.mocked(importDraft).mock.invocationCallOrder[0]).toBeLessThan(jest.mocked(clearSharedPayloads).mock.invocationCallOrder[0]);
  await fireEvent.press(screen.getByRole('button', { name: 'Добавить в этот аккаунт' }));
  expect(assignDraft).toHaveBeenCalledWith('incoming-1', 'account-1');
  expect(router.replace).toHaveBeenCalledWith('/library');
});

test('retains the native payload when SQLite cannot persist it', async () => {
  jest.mocked(importDraft).mockRejectedValueOnce(new Error('sensitive internals'));
  await render(<IncomingShare />);
  expect(screen.getByText(/Не удалось обработать/)).toBeTruthy();
  expect(clearSharedPayloads).not.toHaveBeenCalled();
  expect(screen.queryByText(/sensitive internals/)).toBeNull();
  await fireEvent.press(screen.getByRole('button', { name: 'Повторить' }));
  expect(clearSharedPayloads).toHaveBeenCalledTimes(1);
});

test('refreshes raw data on a warm return and removes its listener', async () => {
  let onChange: (state: AppStateStatus) => void = () => {};
  const remove = jest.fn();
  const subscription = jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener) => {
    onChange = listener;
    return { remove };
  });
  try {
    const view = await render(<IncomingShare />);
    jest.mocked(getSharedPayloads).mockReturnValue([{ shareType: 'text', value: 'Второе сообщение' }]);
    await act(() => onChange('active'));
    expect(screen.getByText('Второе сообщение')).toBeTruthy();
    expect(screen.queryByText('Проверочный текст')).toBeNull();
    await view.unmount();
    expect(remove).toHaveBeenCalled();
  } finally { subscription.mockRestore(); }
});
