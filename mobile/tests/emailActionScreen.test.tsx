import { afterEach, beforeEach, expect, jest, test } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { useAuth } from '../src/auth/context';
import type { AuthController } from '../src/auth/controller';
import { clearEmailAction, receiveEmailLink } from '../src/auth/emailLinks';
import EmailActionScreen from '../src/app/email-action';

jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('../src/auth/config', () => ({ API_ORIGIN: 'https://example.com', STAGING_GATE: false }));
const confirm = jest.fn<AuthController['confirm']>();
beforeEach(() => {
  jest.useFakeTimers();
  confirm.mockResolvedValue(null);
  jest.mocked(useAuth).mockReturnValue({ controller: { confirm } as unknown as AuthController, state: { phase: 'signedOut', busy: false, session: null, message: null } });
});
afterEach(() => { clearEmailAction(); jest.useRealTimers(); });

test('shows confirmation success after the in-memory one-time token is cleared', async () => {
  receiveEmailLink('https://example.com/app/verify.html#token=' + 'a'.repeat(43), 'https://example.com');
  await render(<EmailActionScreen />);
  await fireEvent.press(screen.getByRole('button', { name: 'Подтвердить адрес' }));
  expect(screen.getByText('Адрес электронной почты подтверждён.')).toBeTruthy();
  expect(screen.queryByText('a'.repeat(43))).toBeNull();
});
test('a warm incoming action resets passwords without putting token in visible text', async () => {
  receiveEmailLink('https://example.com/app/reset.html#token=' + 'a'.repeat(43), 'https://example.com');
  await render(<EmailActionScreen />);
  await fireEvent.changeText(screen.getByLabelText('Новый пароль'), 'private-new-password');
  await act(() => { receiveEmailLink('https://example.com/app/reset.html#token=' + 'b'.repeat(43), 'https://example.com'); });
  expect(screen.getByLabelText('Новый пароль').props.value).toBe('');
  expect(screen.queryByText('b'.repeat(43))).toBeNull();
});
