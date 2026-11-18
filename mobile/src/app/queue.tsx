import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Text } from 'react-native';
import { API_ORIGIN } from '../auth/config';
import { useAuth } from '../auth/context';
import { Action, Body, Card, Page, styles } from '../components/ui';
import { Notice, Loading } from '../library/ui';
import { assignDraft, discard, listJobs, ownerKey, retry, subscribe, unassigned, type Draft, type Job } from '../offline/store';

const stateLabel: Record<Job['state'], string> = {
  draft: 'Входящий черновик', pending: 'Сохранено на устройстве · ждёт отправки',
  sending: 'Отправляется', retry_wait: 'Ожидает повтора', needs_auth: 'Нужен вход в исходный аккаунт',
  needs_action: 'Требуется действие', synced: 'Сохранено на сервере',
};
const reasonLabel: Record<string, string> = {
  network: 'Приложение повторит отправку при подключении.', rate: 'Сервер попросил подождать перед повтором.',
  category: 'Категория недоступна. Выберите другую.', invalid: 'Проверьте ссылку или текст.',
  gateway: 'Проверьте доступ к тестовому стенду.', unavailable: 'Сервер пока не принимает очередь.',
  duplicate: 'Эта ссылка уже есть в библиотеке.', deleted: 'Материал был удалён на сервере.',
  expired: 'Срок автоматического повтора истёк. Проверьте библиотеку перед повторным добавлением.',
  conflict: 'Сервер получил другой черновик с этим идентификатором. Проверьте библиотеку.',
  unknown: 'Сервер не подтвердил сохранение. Проверьте библиотеку.',
};

export default function Queue() {
  const { controller, state } = useAuth();
  const ownerId = state.session?.user.id ?? (state.phase === 'offline' ? state.offlineOwner : null);
  const owner = API_ORIGIN && ownerId ? ownerKey(API_ORIGIN, ownerId) : null;
  const [result, setResult] = useState<{ owner: string | null; jobs: Job[] }>();
  const [message, setMessage] = useState('');
  const locked = useRef(false);
  const [busy, setBusy] = useState(false);
  // Drop the previous owner's result before rendering a different session.
  const jobs = result?.owner === owner ? result.jobs : undefined;

  useFocusEffect(useCallback(() => {
    let active = true;
    let revision = 0;
    function load() {
      const requested = ++revision;
      void Promise.all([listJobs(unassigned), owner ? listJobs(owner) : Promise.resolve([])]).then(([inbox, queue]) => {
        if (active && revision === requested) setResult({ owner, jobs: [...inbox, ...queue] });
      }).catch(() => { if (active && revision === requested) setMessage('Не удалось прочитать локальные черновики.'); });
    }
    const unsubscribe = subscribe(load);
    load();
    return () => { active = false; unsubscribe(); };
  }, [owner]));

  async function run(action: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try { await action(); }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Локальная запись не изменилась. Повторите.'); }
    finally { locked.current = false; setBusy(false); }
  }

  function claimDraft(id: string) {
    if (!owner || !ownerId) return;
    const current = controller.snapshot();
    if ((current.session?.user.id ?? (current.phase === 'offline' ? current.offlineOwner : null)) !== ownerId || current.busy) return;
    void run(() => assignDraft(id, owner));
  }

  return <Page title="Очередь и входящие">
    {!jobs && !message && <Loading />}
    {message && <Notice>{message}</Notice>}
    {jobs?.length === 0 && <Body>Черновиков и отправок пока нет.</Body>}
    {jobs?.map(job => {
      const draft = JSON.parse(job.payload) as Draft;
      const invalid = (draft.note?.length ?? 0) > 10_000 || (draft.url?.length ?? 0) > 2_048;
      const editable = (job.state === 'draft' || job.state === 'pending') && job.attempts === 0 ||
        job.state === 'needs_action' && ['invalid', 'category'].includes(job.reason ?? '');
      return <Card key={job.id}>
        <Text style={styles.heading}>{stateLabel[job.state]}</Text>
        {(draft.title || draft.url || draft.note) && <Text numberOfLines={4} style={styles.body}>{draft.title || draft.url || draft.note}</Text>}
        {job.reason && <Notice>{reasonLabel[job.reason]}</Notice>}
        {job.state === 'draft' && (owner ? <>
          <Body>{state.session ? `Получатель · ${state.session.user.email}` : 'Получатель · последний подтверждённый аккаунт'}</Body>
          {invalid && <Notice>Сократите текст или адрес перед добавлением.</Notice>}
          <Action title="Добавить в этот аккаунт" disabled={busy || state.busy || invalid} onPress={() => claimDraft(job.id)} />
        </> : <Action title="Войти для добавления" onPress={() => router.push('/sign-in')} />)}
        {editable && <Action title="Редактировать черновик" disabled={busy} onPress={() => router.push({
          pathname: '/library/[id]', params: { id: 'new', draftId: job.id, ...(job.owner ? {} : { inbox: '1' }) },
        })} />}
        {job.server_id !== null && <Action title="Открыть материал" onPress={() => router.push({
          pathname: '/library/[id]', params: { id: String(job.server_id) },
        })} />}
        {((job.state === 'retry_wait' && job.reason !== 'rate') || ['gateway', 'unavailable'].includes(job.reason ?? '')) &&
          <Action title="Повторить отправку" disabled={busy} onPress={() => void run(() => retry(job.owner, job.id))} />}
        {job.state !== 'sending' && <Action title="Убрать из очереди" disabled={busy} onPress={() => Alert.alert(
          'Убрать локальную запись?', 'Материал на сервере сохраняется, если отправка уже завершилась.', [
            { text: 'Отмена', style: 'cancel' },
            { text: 'Убрать', style: 'destructive', onPress: () => void run(() => discard(job.owner, job.id)) },
          ],
        )} />}
      </Card>;
    })}
  </Page>;
}
