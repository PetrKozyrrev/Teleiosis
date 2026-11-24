import { beforeEach, expect, jest, test } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { Redirect, router } from 'expo-router';
import { useAuth } from '../src/auth/context';
import type { AuthController } from '../src/auth/controller';
import SignIn from '../src/app/sign-in';
import TabsLayout from '../src/app/(tabs)/_layout';

jest.mock('../src/auth/context', () => ({ useAuth: jest.fn() }));
jest.mock('../src/auth/config', () => ({ ...jest.requireActual<Record<string, unknown>>('../src/auth/config'), API_ORIGIN: 'https://example.com', STAGING_GATE: false }));
jest.mock('expo-router', () => ({ router: { replace: jest.fn(), push: jest.fn() }, Redirect: jest.fn(() => null) }));
const signIn = jest.fn<AuthController['signIn']>();
beforeEach(() => {
  signIn.mockResolvedValue();
  jest.mocked(useAuth).mockReturnValue({ controller: { signIn } as unknown as AuthController, state: { phase: 'signedOut', busy: false, session: null, message: null } });
});

test('opens the standalone sign-in route instead of rendering tabs for signed-out users', async () => {
  await render(<TabsLayout />);
  expect(jest.mocked(Redirect).mock.calls[0][0]).toMatchObject({ href: '/sign-in' });
});

test('requires registration consent and hides the password', async () => {
  await render(<SignIn />);
  await fireEvent.press(screen.getByRole('button', { name: 'Создать аккаунт' }));
  await fireEvent.changeText(screen.getByLabelText('Электронная почта'), 'new@example.com');
  await fireEvent.changeText(screen.getByLabelText('Пароль'), 'new-password-42');
  expect(screen.getByLabelText('Пароль').props.secureTextEntry).toBe(true);
  await fireEvent.press(screen.getByRole('button', { name: 'Показать пароль' }));
  expect(screen.getByLabelText('Пароль').props.secureTextEntry).toBe(false);
  await fireEvent.press(screen.getByRole('button', { name: 'Скрыть пароль' }));
  expect(screen.getByLabelText('Пароль').props.secureTextEntry).toBe(true);
  expect(screen.getByRole('button', { name: 'Зарегистрироваться' }).props.accessibilityState.disabled).toBe(true);
  await fireEvent.press(screen.getByRole('checkbox', { name: 'Согласие на обработку персональных данных' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Зарегистрироваться' }));
  expect(signIn).toHaveBeenCalledWith('register', 'new@example.com', 'new-password-42', true);
  expect(router.replace).toHaveBeenCalledWith('/');
});
test('shows controlled errors and clears the transient password after an unsuccessful login', async () => {
  signIn.mockRejectedValue(new Error('Проверьте почту и пароль.'));
  await render(<SignIn />);
  await fireEvent.changeText(screen.getByLabelText('Электронная почта'), 'user@example.com');
  await fireEvent.changeText(screen.getByLabelText('Пароль'), 'private-password');
  await fireEvent.press(screen.getByRole('button', { name: 'Войти' }));
  expect(screen.getByText('Проверьте почту и пароль.')).toBeTruthy();
  expect(screen.getByLabelText('Пароль').props.value).toBe('');
  expect(screen.queryByText('private-password')).toBeNull();
});
