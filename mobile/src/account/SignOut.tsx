import { useState } from 'react';
import { Alert } from 'react-native';
import { useAuth } from '../auth/context';
import { API_ORIGIN } from '../auth/config';
import { Action, Body } from '../components/ui';
import { Notice } from '../library/ui';
import { clearAccount, listJobs, ownerKey } from '../offline/store';
import { useTranslation } from '../i18n';

export function SignOut() {
  const t = useTranslation();
  const { controller, state } = useAuth();
  const isCurrent = controller.captureSession();
  const [message, setMessage] = useState('');
  const [localLogout, setLocalLogout] = useState(false);
  async function exit(localOnly = false) {
    const id = state.session?.user.id ?? state.offlineOwner;
    const owner = API_ORIGIN && id ? ownerKey(API_ORIGIN, id) : null;
    const signOut = async (confirmed: boolean) => {
      setMessage('');
      try {
        await controller.logout(localOnly, owner ? () => clearAccount(owner, confirmed) : undefined, isCurrent);
        setLocalLogout(false);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Не удалось выйти.');
        setLocalLogout(true);
      }
    };
    try {
      const jobs = owner ? await listJobs(owner) : [];
      if (jobs.some(job => job.state !== 'synced')) {
        Alert.alert(t('Удалить черновики и выйти?'), t('Материалы, уже сохранённые на сервере, останутся в библиотеке.'), [
          { text: t('Остаться'), style: 'cancel' },
          { text: t('Удалить и выйти'), style: 'destructive', onPress: () => void signOut(true) },
        ]);
      } else {
        await signOut(false);
      }
    } catch {
      setMessage('Не удалось проверить очередь. Повторите выход.');
    }
  }
  return <>
    <Action variant="danger" title={t('Выйти')} disabled={state.busy} onPress={() => void exit()} />
    {message && <Notice>{message}</Notice>}
    {localLogout && <>
      <Body>{t('Можно удалить сессию только с устройства. Отзыв на сервере не будет подтверждён; серверная сессия завершится по сроку действия.')}</Body>
      <Action variant="outline" title={t('Выйти только на устройстве')} disabled={state.busy} onPress={() => void exit(true)} />
    </>}
  </>;
}
