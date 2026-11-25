import { useState } from 'react';
import { Text } from 'react-native';
import { Redirect, router } from 'expo-router';
import { Action, Body, Card, Page } from '../components/ui';
import { useAuth } from '../auth/context';
import { STAGING_GATE } from '../auth/config';
import { SignOut } from '../account/SignOut';
import { useTranslation } from '../i18n';

export default function Account() {
  const t = useTranslation();
  const { controller, state } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  async function run(action: () => Promise<void>, success?: string) {
    setMessage(null);
    try { await action(); setMessage(success ?? null); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось выполнить действие.'); }
  }
  const user = state.session?.user;
  if (state.phase === 'signedOut') return <Redirect href="/sign-in" />;
  return <Page title={t('Аккаунт')}><Card>
    {state.phase === 'loading' ? <Body>{t('Проверяем сессию…')}</Body> : user ? <>
      <Body>{user.email}</Body>
      <Body>{user.email_verified_at ? t('Почта подтверждена') : t('Почта ещё не подтверждена')}</Body>
      {!user.email_verified_at && <Action title={t('Отправить письмо подтверждения')} disabled={state.busy} onPress={() => void run(() => controller.requestVerification(), 'Запрос принят. Проверьте письмо; на тестовом стенде ссылку читает администратор.')} />}
    </> : <Body>{state.phase === 'offline' ? t('Не удалось проверить сохранённую сессию. Повторите при наличии сети.') : t('Войдите в существующий аккаунт или зарегистрируйтесь.')}</Body>}
    {(message || state.message) && <Text accessibilityLiveRegion="polite">{t(message ?? state.message ?? '')}</Text>}
    {(state.phase === 'error' || state.phase === 'offline') && <Action variant="outline" title={t('Повторить проверку сессии')} disabled={state.busy} onPress={() => void run(() => state.phase === 'error' ? controller.initialize() : controller.refresh())} />}
    {(user || state.phase === 'offline' || state.phase === 'error') && <SignOut />}
    <Action title={t('Открыть ссылку из письма')} disabled={state.busy} onPress={() => router.push('/email-action')} />
    {STAGING_GATE && <Action title={t('Доступ к тестовому стенду')} disabled={state.busy} onPress={() => router.push('/staging-access')} />}
  </Card></Page>;
}
