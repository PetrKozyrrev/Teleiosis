import { useState } from 'react';
import { Text } from 'react-native';
import { Redirect } from 'expo-router';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { useAuth } from '../auth/context';
import { API_ORIGIN, STAGING_GATE } from '../auth/config';
import { vault } from '../auth/vault';

export default function StagingAccess() {
  const { controller, state } = useAuth();
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  if (!STAGING_GATE || !API_ORIGIN) return <Redirect href="/account" />;
  async function save() {
    setBusy(true);
    try {
      await vault.setGateway(API_ORIGIN!, password);
      setPassword(''); setMessage('Доступ сохранён на устройстве. Теперь можно войти в аккаунт.');
      await controller.refresh();
    } catch { setPassword(''); setMessage('Не удалось сохранить или проверить доступ. Повторите на разблокированном устройстве.'); }
    finally { setBusy(false); }
  }
  return <Page title="Закрытый тестовый стенд"><Card>
    <Body>Администратор выдаёт отдельный пароль доступа к стенду. Это не пароль вашего аккаунта.</Body>
    <Body>Письма остаются у администратора. Используйте только вымышленные данные.</Body>
    <Field label="Пароль доступа к стенду" value={password} onChangeText={setPassword} secureTextEntry autoComplete="off" maxLength={256} editable={!busy && !state.busy} />
    <Action title="Сохранить доступ" disabled={busy || state.busy || !password} onPress={() => void save()} />
    {message && <Text accessibilityLiveRegion="polite">{message}</Text>}
  </Card></Page>;
}
