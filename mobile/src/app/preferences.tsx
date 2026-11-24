import { useRef, useState } from 'react';
import { Alert } from 'react-native';
import { router } from 'expo-router';
import { useAuth } from '../auth/context';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { LibraryAccess, Notice } from '../library/ui';
import { errorMessage, type Request } from '../library/model';
import { AccountReminders } from '../account/AccountReminders';
import { exportAccount } from '../account/export';
import { clearDeletedData } from '../account/cleanup';

export default function Preferences() {
  return <LibraryAccess>{(request, owner) => <PreferencesView request={request} owner={owner} />}</LibraryAccess>;
}

function PreferencesView({ request, owner }: { request: Request; owner: string | null }) {
  const { controller, state } = useAuth();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);

  async function run(action: () => Promise<void>, success: string, accountDeletion = false) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setMessage('');
    try { await action(); setMessage(success); }
    catch (error) { setMessage(accountDeletion && controller.snapshot().message ? controller.snapshot().message! :
        error instanceof ApiError && error.status === 400 ? 'Проверьте текущий пароль.' :
        error instanceof ApiError ? errorMessage(error, 'Проверьте введённые данные.') :
        'Не удалось завершить действие. Проверьте доступность хранилища и повторите.'); }
    finally { locked.current = false; setBusy(false); setOldPassword(''); setNewPassword(''); setDeletePassword(''); }
  }

  function removeAccount() {
    if (!owner || !deletePassword || busy) return;
    Alert.alert('Удалить аккаунт навсегда?', 'Будут удалены серверные данные, очередь, кэш и входящие черновики на этом устройстве.', [
      { text: 'Отмена', style: 'cancel', onPress: () => setDeletePassword('') },
      { text: 'Удалить аккаунт', style: 'destructive', onPress: () => void run(async () => {
        await controller.deleteAccount(deletePassword, () => clearDeletedData(owner), state.session?.user.id ?? state.offlineOwner ?? undefined);
        router.replace('/');
      }, 'Аккаунт удалён.', true) },
    ]);
  }
  const disabled = busy || state.busy;
  return <Page title="Пароль и данные">
    <AccountReminders request={request} />
    <Card>
      <Body>Сменить пароль</Body>
      <Field label="Текущий пароль" value={oldPassword} onChangeText={setOldPassword} secureTextEntry editable={!disabled} maxLength={128} />
      <Field label="Новый пароль" value={newPassword} onChangeText={setNewPassword} secureTextEntry editable={!disabled} maxLength={128} />
      <Action title="Сохранить новый пароль" disabled={disabled || !oldPassword || newPassword.length < 10} onPress={() => void run(async () => {
        await request('/auth/change-password', 'POST', { current_password: oldPassword, new_password: newPassword });
      }, 'Пароль изменён. Остальные сессии закрыты.')} />
    </Card>
    <Card>
      <Body>Выгрузка включает данные, сохранённые на сервере. Ожидающие отправки черновики доступны в очереди.</Body>
      <Action title="Выгрузить данные" disabled={disabled} onPress={() => void run(() =>
        exportAccount(request, () => Boolean(state.session && controller.snapshot().session?.user.id === state.session.user.id)),
      'Системное меню выгрузки закрыто.')} />
      <Action title="Импортировать выгрузку" disabled={disabled} onPress={() => router.push('/library/import')} />
    </Card>
    <Card>
      <Field label="Пароль для удаления аккаунта" value={deletePassword} onChangeText={setDeletePassword} secureTextEntry editable={!disabled} maxLength={128} />
      <Action title="Удалить аккаунт" disabled={disabled || !deletePassword || !owner} onPress={removeAccount} />
    </Card>
    {message && <Notice>{message}</Notice>}
  </Page>;
}
