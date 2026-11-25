import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Text } from 'react-native';
import { API_ORIGIN } from '../auth/config';
import { useAuth } from '../auth/context';
import { Action, Body, Card, styles } from '../components/ui';
import { assignDraft, discard, listJobs, ownerKey, retry, subscribe, unassigned, type Draft, type Job } from '../offline/store';
import { Notice } from './ui';
import { useTranslation } from '../i18n';

const stateLabel: Record<Job['state'], string> = {
  draft: 'Входящий черновик', pending: 'Сохранено на устройстве · ждёт отправки',
  sending: 'Отправляется', retry_wait: 'Ожидает повтора', needs_auth: 'Нужен вход в исходный аккаунт',
  needs_action: 'Требуется действие', synced: 'Сохранено на сервере',
};
const reasonLabel: Record<string, string> = {
  network: 'Приложение повторит отправку при подключении.', rate: 'Сервер попросил подождать перед повтором.',
  category: 'Категория недоступна. Выберите другую.', collection: 'Коллекция недоступна. Измените выбор.', invalid: 'Проверьте ссылку или текст.',
  gateway: 'Проверьте доступ к тестовому стенду.', unavailable: 'Сервер пока не принимает материалы.',
  duplicate: 'Эта ссылка уже есть в библиотеке.', deleted: 'Материал был удалён на сервере.',
  expired: 'Срок автоматического повтора истёк. Проверьте библиотеку перед повторным добавлением.',
  conflict: 'Сервер получил другой черновик с этим идентификатором. Проверьте библиотеку.',
  unknown: 'Сервер не подтвердил сохранение. Проверьте библиотеку.',
};

export function PendingMaterials({ owner, inboxOnly = false, failuresOnly = false, excludeId, onAssigned }: {
  owner: string | null; inboxOnly?: boolean; failuresOnly?: boolean; excludeId?: string; onAssigned?: () => void;
}) {
  const t = useTranslation();
  const [result, setResult] = useState<{ source: string; jobs: Job[] }>();
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const source = failuresOnly ? owner : unassigned;
  const jobs = result?.source === source ? result.jobs.filter(job => job.id !== excludeId) : undefined;

  useFocusEffect(useCallback(() => {
    if (source === null) return;
    let active = true;
    let revision = 0;
    const load = () => {
      const requested = ++revision;
      void listJobs(source)
        .then(rows => {
          if (!active || requested !== revision) return;
          setResult({ source, jobs: failuresOnly ? rows.filter(job => job.state === 'needs_action') : rows });
          setError(false);
        }).catch(() => { if (active && requested === revision) setError(true); });
    };
    const unsubscribe = subscribe(load);
    load();
    return () => { active = false; unsubscribe(); };
  }, [source, failuresOnly]));

  return <>
    {error && <Notice>{t('Не удалось прочитать локальные черновики.')}</Notice>}
    {inboxOnly && jobs?.length === 0 && <Body>{t('Входящих материалов пока нет.')}</Body>}
    {jobs && jobs.length > 0 && <Card>
      {!inboxOnly && <Action variant={failuresOnly ? 'text' : 'outline'}
        title={`${failuresOnly ? t('Ошибки отправки') : t('Входящие материалы')} · ${jobs.length}`}
        onPress={() => setExpanded(current => !current)} />}
      {(inboxOnly || expanded) && jobs.map(job => {
        const draft = JSON.parse(job.payload) as Draft;
        return <Card key={job.id}>
          <Text style={styles.label}>{t(stateLabel[job.state])}</Text>
          <Text numberOfLines={4} selectable style={styles.body}>{draft.title || draft.url || draft.note}</Text>
          <PendingMaterialActions job={job} owner={owner} onAssigned={onAssigned} />
        </Card>;
      })}
    </Card>}
  </>;
}

export function PendingMaterialActions({ job, owner, onAssigned, onDiscarded }: {
  job: Job; owner: string | null; onAssigned?: () => void; onDiscarded?: () => void;
}) {
  const t = useTranslation();
  const { controller, state } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const locked = useRef(false);
  const isCurrent = controller.captureSession();
  const draft = JSON.parse(job.payload) as Draft;
  const invalid = (draft.note?.length ?? 0) > 10_000 || (draft.url?.length ?? 0) > 2_048;
  const editable = (job.state === 'draft' || job.state === 'pending') && job.attempts === 0 ||
    job.state === 'needs_action' && ['invalid', 'category', 'collection'].includes(job.reason ?? '');
  const disabled = busy || state.busy;

  if (job.owner && job.owner !== owner) return null;

  async function run(action: () => Promise<void>) {
    if (locked.current || !isCurrent() || controller.snapshot().busy) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try { await action(); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Локальная запись не изменилась. Повторите.'); }
    finally { locked.current = false; setBusy(false); }
  }

  function claimDraft() {
    const current = controller.snapshot();
    const id = current.session?.user.id ?? (current.phase === 'offline' ? current.offlineOwner : null);
    if (!owner || !API_ORIGIN || !id || ownerKey(API_ORIGIN, id) !== owner) return;
    void run(async () => {
      await assignDraft(job.id, owner);
      if (isCurrent()) onAssigned?.();
    });
  }

  return <>
    {message && <Notice>{message}</Notice>}
    {job.reason && <Notice>{reasonLabel[job.reason]}</Notice>}
    {job.state === 'draft' && (owner ? <>
      <Body>{state.session ? t('Получатель · {0}', state.session.user.email) : t('Получатель · последний подтверждённый аккаунт')}</Body>
      {invalid && <Notice>{t('Сократите текст или адрес перед добавлением.')}</Notice>}
      <Action title={t('Добавить в этот аккаунт')} disabled={disabled || invalid} onPress={claimDraft} />
    </> : <Action title={t('Войти для добавления')} onPress={() => router.push('/sign-in')} />)}
    {editable && <Action variant="outline" title={t('Редактировать черновик')} disabled={disabled} onPress={() => router.push({
      pathname: '/library/[id]', params: { id: 'new', draftId: job.id, ...(job.owner ? {} : { inbox: '1' }) },
    })} />}
    {job.server_id !== null && <Action variant="outline" title={t('Открыть материал')} onPress={() => router.push({
      pathname: '/library/[id]', params: { id: String(job.server_id) },
    })} />}
    {((job.state === 'retry_wait' && job.reason !== 'rate') || ['gateway', 'unavailable'].includes(job.reason ?? '')) &&
      <Action variant="outline" title={t('Повторить отправку')} disabled={disabled} onPress={() => void run(() => retry(job.owner, job.id))} />}
    {job.state !== 'sending' && <Action variant="danger" title={t('Убрать локальную запись')} disabled={disabled} onPress={() => Alert.alert(
      t('Убрать локальную запись?'), t('Сохранённый на сервере материал останется в библиотеке.'), [
        { text: t('Отмена'), style: 'cancel' },
        { text: t('Убрать'), style: 'destructive', onPress: () => void run(async () => {
          await discard(job.owner, job.id);
          if (isCurrent()) onDiscarded?.();
        }) },
      ],
    )} />}
  </>;
}
