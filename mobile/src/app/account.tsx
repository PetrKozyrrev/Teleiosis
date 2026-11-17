import { useState } from 'react';
import { Text } from 'react-native';
import { router } from 'expo-router';
import { Action, Body, Card, Page } from '../components/ui';
import { useAuth } from '../auth/context';
import { STAGING_GATE } from '../auth/config';

export default function Account() {
  const { controller, state } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [localLogout, setLocalLogout] = useState(false);
  async function run(action: () => Promise<void>, success?: string, logout = false) {
    setMessage(null);
    try { await action(); setMessage(success ?? null); setLocalLogout(false); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось выполнить действие.'); if (logout) setLocalLogout(true); }
  }
  const user = state.session?.user;
  return <Page title="Аккаунт"><Card>
    {state.phase === 'loading' ? <Body>Проверяем сессию…</Body> : user ? <>
      <Body>{user.email}</Body>
      <Body>{user.email_verified_at ? 'Почта подтверждена' : 'Почта ещё не подтверждена'}</Body>
      {!user.email_verified_at && <Action title="Отправить письмо подтверждения" disabled={state.busy} onPress={() => void run(() => controller.requestVerification(), 'Запрос принят. Проверьте письмо; на тестовом стенде ссылку читает администратор.')} />}
    </> : <Body>{state.phase === 'offline' ? 'Не удалось проверить сохранённую сессию. Повторите при наличии сети.' : 'Войдите в существующий аккаунт или зарегистрируйтесь.'}</Body>}
    {(message || state.message) && <Text accessibilityLiveRegion="polite">{message ?? state.message}</Text>}
    {state.phase === 'signedOut' && <Action title="Войти или зарегистрироваться" disabled={state.busy} onPress={() => router.push('/sign-in')} />}
    {(state.phase === 'error' || state.phase === 'offline' || user) && <Action title="Повторить проверку сессии" disabled={state.busy} onPress={() => void run(() => state.phase === 'error' ? controller.initialize() : controller.refresh())} />}
    {(user || state.phase === 'offline' || state.phase === 'error') && <Action title="Выйти" disabled={state.busy} onPress={() => void run(() => controller.logout(), undefined, true)} />}
    {localLogout && <>
      <Body>Можно удалить сессию только с устройства. Отзыв на сервере не будет подтверждён; серверная сессия завершится по сроку действия.</Body>
      <Action title="Выйти только на устройстве" disabled={state.busy} onPress={() => void run(() => controller.logout(true))} />
    </>}
    <Action title="Открыть ссылку из письма" disabled={state.busy} onPress={() => router.push('/email-action')} />
    {STAGING_GATE && <Action title="Доступ к тестовому стенду" disabled={state.busy} onPress={() => router.push('/staging-access')} />}
  </Card></Page>;
}
