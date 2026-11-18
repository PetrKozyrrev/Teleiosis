import { useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import { router } from 'expo-router';
import { useAuth } from '../auth/context';
import { ApiError, type User } from '../auth/api';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { Choice, LibraryAccess, Loading, Notice } from '../library/ui';
import { errorMessage, type Request } from '../library/model';
import { AccountReminders } from '../account/AccountReminders';
import { exportAccount } from '../account/export';
import { clearDeletedData } from '../account/cleanup';

export default function Preferences() {
  return <LibraryAccess>{(request, owner) => <PreferencesView request={request} owner={owner} />}</LibraryAccess>;
}

function PreferencesView({ request, owner }: { request: Request; owner: string | null }) {
  const { controller, state } = useAuth();
  const [profile, setProfile] = useState<User>();
  const [timezone, setTimezone] = useState('');
  const [time, setTime] = useState('');
  const [enabled, setEnabled] = useState('on');
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  useEffect(() => {
    let active = true;

    void request('/me', 'GET').then(value => {
      if (!active) return;
      const user = value as User;
      setProfile(user); setTimezone(user.timezone); setTime(user.reminder_time); setEnabled(user.reminders_enabled ? 'on' : 'off');
    }).catch(error => { if (active) setMessage(errorMessage(error)); });
    return () => { active = false; };
  }, [request, revision]);

  async function run(action: () => Promise<void>, success: string, accountDeletion = false) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setMessage('');
    try { await action(); setMessage(success); }
    catch (error) { setMessage(accountDeletion && controller.snapshot().message ? controller.snapshot().message! :
        error instanceof ApiError && error.status === 400 ? 'Проверьте текущий пароль.' :
        error instanceof ApiError ? errorMessage(error, 'Проверьте часовой пояс, время и введённые данные.') :
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
  return <Page title="Настройки аккаунта">
    {!profile && !message && <Loading />}
    {profile && <Card>
      <Body>{profile.email}</Body>
      <Field label="Часовой пояс IANA" value={timezone} onChangeText={setTimezone} editable={!disabled} maxLength={100} />
      <Action title="Использовать пояс устройства" disabled={disabled} onPress={() => setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone)} />
      <Field label="Время ежедневной подборки (ЧЧ:ММ)" value={time} onChangeText={setTime} editable={!disabled} maxLength={5} />
      <Choice label="Письма с напоминаниями" value={enabled} onChange={setEnabled} disabled={disabled}
        options={[{ value: 'on', label: 'Включены' }, { value: 'off', label: 'Выключены' }]} />
      <Body>Время подборки задаётся в выбранном часовом поясе. Для доставки нужна подтверждённая почта. На тестовом стенде письма доступны администратору.</Body>
      <Action title="Сохранить настройки" disabled={disabled} onPress={() => void run(async () => {
        await request('/me/settings', 'PATCH', { timezone: timezone.trim(), reminder_time: time, reminders_enabled: enabled === 'on' });
        await controller.refresh();
      }, 'Настройки сохранены.')} />
    </Card>}
    <Action title="Обновить настройки" disabled={disabled} onPress={() => { setProfile(undefined); setRevision(value => value + 1); }} />
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
    </Card>
    <Card>
      <Field label="Пароль для удаления аккаунта" value={deletePassword} onChangeText={setDeletePassword} secureTextEntry editable={!disabled} maxLength={128} />
      <Action title="Удалить аккаунт" disabled={disabled || !deletePassword || !owner} onPress={removeAccount} />
    </Card>
    {message && <Notice>{message}</Notice>}
  </Page>;
}
