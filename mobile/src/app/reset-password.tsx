import { useState } from 'react';
import { Text } from 'react-native';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { useAuth } from '../auth/context';
import { API_ORIGIN } from '../auth/config';

export default function ResetPassword() {
  const { controller, state } = useAuth();
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  async function submit() {
    try { await controller.requestReset(email.trim()); setMessage('Если адрес зарегистрирован, ссылка отправлена. На тестовом стенде письмо перехватывает администратор.'); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось отправить запрос.'); }
  }
  return <Page title="Восстановить доступ"><Card>
    <Body>Введите почту аккаунта. Ответ одинаков для зарегистрированного и неизвестного адреса.</Body>
    <Field label="Электронная почта" value={email} onChangeText={setEmail} keyboardType="email-address" autoComplete="email" maxLength={320} editable={!state.busy} />
    <Action title="Запросить ссылку" disabled={!API_ORIGIN || state.busy || !email.trim()} onPress={() => void submit()} />
    {message && <Text accessibilityLiveRegion="polite">{message}</Text>}
  </Card></Page>;
}
