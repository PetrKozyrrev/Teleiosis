import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Field } from '../components/ui';
import { Notice } from '../library/ui';
import { errorMessage, type Request } from '../library/model';
import { reminderInstant } from './reminderTime';
import { useLocale, useTranslation } from '../i18n';

export function Reminder({ id, request }: { id: number; request: Request }) {
  const t = useTranslation();
  const locale = useLocale();
  const [current, setCurrent] = useState<{ scheduled_at: string } | null>();
  const [date, setDate] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const generation = useRef(0);
  const [revision, setRevision] = useState(0);
  const path = `/contents/${id}/reminder` as const;
  useEffect(() => {
    let active = true;
    const expected = generation.current;
    void request(path, 'GET').then(value => {
      if (active && expected === generation.current) { setCurrent(value as typeof current); setMessage(''); }
    }).catch(error => { if (active) setMessage(errorMessage(error)); });
    return () => { active = false; };
  }, [path, request, revision]);
  async function update(remove = false) {
    if (lock.current) return;
    generation.current += 1;
    lock.current = true; setBusy(true); setMessage('');
    try {
      const result = remove ? await request(path, 'DELETE') :
        await request(path, 'PUT', { scheduled_at: reminderInstant(date.trim()) });
      setCurrent(remove ? null : result as typeof current);
      setMessage(remove ? 'Напоминание отменено.' : 'Напоминание сохранено.');
    } catch (error) {
      setMessage(error instanceof ApiError && error.status === 409
        ? 'Напоминание изменилось или достигнут лимит. Обновите его и проверьте другие напоминания.'
        : error instanceof Error && !(error instanceof ApiError) ? error.message : errorMessage(error, 'Проверьте время напоминания.'));
    } finally { lock.current = false; setBusy(false); }
  }
  return <Card>
    <Body>{t('Напоминание')}</Body>
    <Body>{current ? new Date(current.scheduled_at).toLocaleString(locale) : current === null ? t('Не задано') : t('Загрузка…')}</Body>
    <Body>{t('Время со смещением UTC, например 2026-12-01T10:00+03:00. Доставка письма зависит от подтверждения почты и настроек напоминаний.')}</Body>
    <Field label={t('Дата и время напоминания')} value={date} onChangeText={setDate} editable={!busy} maxLength={22} />
    <Action title={current ? t('Перенести напоминание') : t('Назначить напоминание')} disabled={busy || !date || current === undefined} onPress={() => void update()} />
    {current && <Action title={t('Отменить напоминание')} disabled={busy} onPress={() => void update(true)} />}
    <Action title={t('Обновить напоминание')} disabled={busy} onPress={() => { setCurrent(undefined); setRevision(value => value + 1); }} />
    {message && <Notice>{message}</Notice>}
  </Card>;
}
