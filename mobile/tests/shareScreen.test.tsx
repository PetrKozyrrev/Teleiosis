import { beforeEach, expect, jest, test } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';
import { router } from 'expo-router';
import { clearSharedPayloads, getSharedPayloads } from 'expo-sharing';
import ShareProbe from '../src/app/share-probe';

jest.mock('expo-router', () => ({ router: { replace: jest.fn() } }));
jest.mock('expo-sharing', () => ({ getSharedPayloads: jest.fn(), clearSharedPayloads: jest.fn() }));

beforeEach(() => {
  jest.mocked(getSharedPayloads).mockReturnValue([{ shareType: 'text', value: 'Проверочный текст' }]);
  jest.mocked(clearSharedPayloads).mockImplementation(() => {});
});

test('previews, clears, and can receive the same text again', async () => {
  const first = await render(<ShareProbe />);
  expect(screen.getByText('Проверочный текст')).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Очистить и закрыть' }));
  expect(clearSharedPayloads).toHaveBeenCalledTimes(1);
  expect(router.replace).toHaveBeenCalledWith('/');
  expect(screen.queryByText('Проверочный текст')).toBeNull();
  await first.unmount();
  await render(<ShareProbe />);
  expect(screen.getByText('Проверочный текст')).toBeTruthy();
});

test('handles native errors without displaying payloads or exception internals', async () => {
  jest.mocked(getSharedPayloads).mockImplementation(() => { throw new Error('sensitive internals'); });
  await render(<ShareProbe />);
  expect(screen.getByText(/Не удалось прочитать/)).toBeTruthy();
  expect(screen.queryByText(/sensitive internals/)).toBeNull();
});

test('does not claim a successful discard when native clear fails', async () => {
  jest.mocked(clearSharedPayloads).mockImplementation(() => { throw new Error('native failure'); });
  await render(<ShareProbe />);
  await fireEvent.press(screen.getByRole('button', { name: 'Очистить и закрыть' }));
  expect(screen.getByText(/Не удалось прочитать/)).toBeTruthy();
  expect(router.replace).not.toHaveBeenCalled();
});

test('refreshes raw data on a warm return and removes its listener', async () => {
  let onChange: (state: AppStateStatus) => void = () => {};
  const remove = jest.fn();
  const subscription = jest.spyOn(AppState, 'addEventListener').mockImplementation((_, listener) => {
    onChange = listener;
    return { remove };
  });
  try {
    const view = await render(<ShareProbe />);
    jest.mocked(getSharedPayloads).mockReturnValue([{ shareType: 'text', value: 'Второе сообщение' }]);
    await act(() => onChange('active'));
    expect(screen.getByText('Второе сообщение')).toBeTruthy();
    expect(screen.queryByText('Проверочный текст')).toBeNull();
    await view.unmount();
    expect(remove).toHaveBeenCalled();
  } finally { subscription.mockRestore(); }
});
