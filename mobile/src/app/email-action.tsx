import { useState, useSyncExternalStore } from 'react';
import { Text } from 'react-native';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { useAuth } from '../auth/context';
import { API_ORIGIN } from '../auth/config';
import { clearEmailAction, emailActionSnapshot, receiveEmailLink, subscribeEmailActions, type EmailAction } from '../auth/emailLinks';
import { useTranslation } from '../i18n';

export default function EmailActionScreen() {
  const action = useSyncExternalStore(subscribeEmailActions, emailActionSnapshot, emailActionSnapshot);
  const [notice, setNotice] = useState<string | null>(null);
  return <EmailActionForm key={action?.id ?? 'empty'} action={action} notice={notice} onResult={setNotice} />;
}

function EmailActionForm({ action, notice, onResult }: { action: EmailAction | null; notice: string | null; onResult: (value: string | null) => void }) {
  const t = useTranslation();
  const { controller, state } = useAuth();
  const [link, setLink] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  function open() {
    const accepted = receiveEmailLink(link.trim(), API_ORIGIN);
    setLink('');
    setMessage(accepted ? null : 'Нужна действующая HTTPS-ссылка сброса или подтверждения с адреса нашего сервера.');
  }
  async function confirm() {
    if (!action) return;
    try {
      const warning = await controller.confirm(action.kind, action.token, password);
      const result = action.kind === 'reset' ? 'Пароль изменён. Войдите с новым паролем.' : 'Адрес электронной почты подтверждён.';
      onResult(warning ?? result);
      clearEmailAction(action.id);
    } catch (error) { setPassword(''); setRepeat(''); setMessage(error instanceof Error ? error.message : 'Не удалось применить ссылку.'); }
  }
  return <Page title={action?.kind === 'reset' ? t('Новый пароль') : action?.kind === 'verify' ? t('Подтвердить почту') : t('Ссылка из письма')}><Card>
    {action ? <>
      <Body>{action.kind === 'reset' ? t('После сброса все сессии этого аккаунта завершатся. Потребуется войти заново.') : t('Подтвердите адрес электронной почты по полученной ссылке.')}</Body>
      {action.kind === 'reset' && <>
        <Field label={t('Новый пароль')} value={password} onChangeText={setPassword} secureTextEntry autoComplete="new-password" textContentType="newPassword" maxLength={128} editable={!state.busy} />
        <Field label={t('Повторите новый пароль')} value={repeat} onChangeText={setRepeat} secureTextEntry maxLength={128} editable={!state.busy} />
      </>}
      <Action title={action.kind === 'reset' ? t('Изменить пароль') : t('Подтвердить адрес')} disabled={state.busy || (action.kind === 'reset' && (password.length < 10 || password !== repeat))} onPress={() => void confirm()} />
      <Action title={t('Отменить')} disabled={state.busy} onPress={() => { onResult(null); clearEmailAction(action.id); }} />
    </> : <>
      <Body>{t('Откройте ссылку из письма или вставьте её сюда. Текст ссылки не сохраняется.')}</Body>
      <Field label={t('Ссылка из письма')} value={link} onChangeText={setLink} secureTextEntry autoComplete="off" editable={!state.busy} maxLength={2048} />
      <Action title={t('Открыть ссылку')} disabled={state.busy || !link.trim()} onPress={open} />
    </>}
    {message && <Text accessibilityLiveRegion="polite">{t(message)}</Text>}
    {!action && !message && notice && <Text accessibilityLiveRegion="polite">{t(notice)}</Text>}
  </Card></Page>;
}
