import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/context';
import type { User } from '../auth/api';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { errorMessage, type Request } from '../library/model';
import { LibraryAccess, Loading, Notice } from '../library/ui';

export default function ReadingSchedule() {
  return <LibraryAccess title="Время и часовой пояс">{request => <ScheduleForm request={request} />}</LibraryAccess>;
}

function ScheduleForm({ request }: { request: Request }) {
  const { controller, state } = useAuth();
  const [schedule, setSchedule] = useState<{ timezone: string; reminder_time: string }>();
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);

  useEffect(() => {
    let active = true;
    void request('/me', 'GET').then(value => {
      const user = value as User;
      if (active) setSchedule(current => current ?? { timezone: user.timezone, reminder_time: user.reminder_time });
    }).catch(error => { if (active) setMessage(errorMessage(error)); });
    return () => { active = false; };
  }, [request, revision]);

  async function save() {
    if (!schedule || locked.current) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try {
      const saved = await request('/me/settings', 'PATCH', { ...schedule, timezone: schedule.timezone.trim() }) as User;
      setSchedule({ timezone: saved.timezone, reminder_time: saved.reminder_time });
      await controller.refresh().catch(() => {});
      setMessage('Настройки сохранены.');
    } catch (error) {
      setMessage(errorMessage(error, 'Проверьте часовой пояс и время.'));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  const disabled = busy || state.busy || state.phase === 'offline';
  return <Page title="Время и часовой пояс" subtitle="Когда присылать подборку для чтения">
    {schedule ? <Card>
      <Field label="Время ежедневной подборки (ЧЧ:ММ)" value={schedule.reminder_time}
        onChangeText={reminder_time => setSchedule({ ...schedule, reminder_time })} maxLength={5} editable={!disabled} />
      <Field label="Часовой пояс" value={schedule.timezone} onChangeText={timezone => setSchedule({ ...schedule, timezone })}
        placeholder="Europe/Moscow" editable={!disabled} maxLength={100} />
      <Action variant="outline" title="Использовать пояс телефона" disabled={disabled}
        onPress={() => setSchedule({ ...schedule, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })} />
      <Body>Для доставки нужна подтверждённая почта и включённые напоминания.</Body>
      <Action title="Сохранить настройки" disabled={disabled || !schedule.timezone.trim() || !/^([01]\d|2[0-3]):[0-5]\d$/.test(schedule.reminder_time)}
        onPress={() => void save()} />
    </Card> : message ? <Action variant="outline" title="Повторить загрузку" onPress={() => { setMessage(''); setRevision(value => value + 1); }} /> : <Loading />}
    {message && <Notice>{message}</Notice>}
  </Page>;
}
