import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { useTranslation } from '../i18n';
import { errorMessage, initialFilters, listPath, statuses, type Material, type Request } from '../library/model';
import { Choice, Loading, Notice } from '../library/ui';

const path = '/mobile/learning/goals';
const limit = 20;
const goalStatuses = { active: 'Активные', completed: 'Завершённые', archived: 'Архивные' };
type Status = keyof typeof goalStatuses;
type Goal = {
  id: number; name: string; result: string | null; status: Status; version: number;
  materials_total: number; materials_studied: number; linked?: boolean;
};
type GoalMaterial = Pick<Material, 'id' | 'title' | 'status'>;
type ResultPage<T> = { items: T[]; total: number };

function goalError(error: unknown) {
  if (error instanceof ApiError && !error.gateway) {
    if (error.code === 'goal_name_taken') return 'Цель с таким названием уже существует.';
    if (error.code === 'goal_limit') return 'Достигнут лимит в 100 целей.';
    if (error.status === 404) return 'Цель или материал недоступны. Для целей требуется API E2.';
    if (error.status === 412) return 'Цель изменилась. Обновите её перед сохранением.';
    if (error.status === 0) return 'Для работы с целями нужно подключение к серверу.';
  }
  return errorMessage(error);
}

function useGoalData<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const epoch = useRef(0);
  const saving = useRef(false);
  const refresh = () => setRevision(value => value + 1);

  useFocusEffect(useCallback(() => {
    void revision;
    const current = ++epoch.current;
    setData(undefined);
    setBusy(false);
    setMessage('');
    saving.current = false;
    void load().then(value => { if (current === epoch.current) setData(value); })
      .catch(error => { if (current === epoch.current) setMessage(goalError(error)); });
    return () => { epoch.current++; };
  }, [load, revision]));

  async function save(operation: () => Promise<unknown>, done?: (value: unknown) => void) {
    if (saving.current) return;
    const current = epoch.current;
    saving.current = true;
    setBusy(true);
    setMessage('');
    try {
      const value = await operation();
      if (current === epoch.current) {
        done?.(value);
        refresh();
      }
    } catch (error) {
      if (current === epoch.current) setMessage(goalError(error));
    } finally {
      if (current === epoch.current) {
        setBusy(false);
        saving.current = false;
      }
    }
  }
  return { data, message, busy, refresh, save };
}

function Steps({ offset, total, change, disabled }: {
  offset: number; total: number; change: (value: number) => void; disabled?: boolean;
}) {
  const t = useTranslation();
  return <>
    {offset > 0 && <Action variant="outline" title={t('Предыдущая страница')} disabled={disabled} onPress={() => change(Math.max(0, offset - limit))} />}
    {offset + limit < total && <Action variant="outline" title={t('Следующая страница')} disabled={disabled} onPress={() => change(offset + limit)} />}
  </>;
}

function GoalProgress({ goal }: { goal: Goal }) {
  const t = useTranslation();
  return <Body>{goal.materials_total
    ? t('Изучено материалов: {0} из {1}', goal.materials_studied, goal.materials_total)
    : t('Добавьте материалы')}</Body>;
}

function GoalFields({ name, result, setName, setResult, busy }: {
  name: string; result: string; setName: (value: string) => void; setResult: (value: string) => void; busy: boolean;
}) {
  const t = useTranslation();
  return <>
    <Field label={t('Название цели')} value={name} onChangeText={setName} editable={!busy} maxLength={100} />
    <Field label={t('Желаемый результат (необязательно)')} value={result} onChangeText={setResult}
      editable={!busy} maxLength={4000} multiline />
  </>;
}

export function GoalsList({ request, contentId }: { request: Request; contentId?: number }) {
  const t = useTranslation();
  const [status, setStatus] = useState<Status>('active');
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [result, setResult] = useState('');
  const load = useCallback(async () => await request(
    `${path}?status=${status}&limit=${limit}&offset=${offset}${contentId ? `&content_id=${contentId}` : ''}`, 'GET',
  ) as ResultPage<Goal>, [contentId, offset, request, status]);
  const { data, busy, message, refresh, save } = useGoalData(load);
  return <Page title={t(contentId ? 'Добавить к цели' : 'Цели')}>
    <Choice label={t('Статус целей')} options={(Object.keys(goalStatuses) as Status[]).map(value => ({
      value, label: t(goalStatuses[value]),
    }))} value={status} disabled={busy} onChange={value => { setStatus(value); setOffset(0); }} />
    {message && <Notice>{message}</Notice>}
    {!data && !message && <Loading />}
    {data && <>
      {!data.items.length && <Body>{t('В этом списке пока нет целей.')}</Body>}
      {data.items.map(goal => <Card key={goal.id}>
        <Body>{goal.name}</Body>
        <GoalProgress goal={goal} />
        {contentId ? <>
          {goal.linked && <Body>{t('Материал уже связан с целью.')}</Body>}
          <Action variant="outline" title={t(goal.linked ? 'Отвязать материал' : 'Привязать материал')} disabled={busy}
            onPress={() => void save(() => goal.linked
              ? request(`${path}/${goal.id}/materials/${contentId}`, 'DELETE')
              : request(`${path}/${goal.id}/materials`, 'POST', { content_id: contentId }))} />
        </> : <Action title={t('Открыть цель')} onPress={() => router.push({
          pathname: '/goals/[id]', params: { id: String(goal.id) },
        })} />}
      </Card>)}
      <Steps offset={offset} total={data.total} change={setOffset} disabled={busy} />
    </>}
    {!contentId && (creating ? <Card>
      <GoalFields name={name} result={result} setName={setName} setResult={setResult} busy={busy} />
      <Action title={t('Создать цель')} disabled={busy || !name.trim()} onPress={() => void save(
        () => request(path, 'POST', { name: name.trim(), result: result.trim() || null }),
        value => {
          setCreating(false); setName(''); setResult('');
          router.push({ pathname: '/goals/[id]', params: { id: String((value as Goal).id) } });
        },
      )} />
      <Action variant="text" title={t('Отмена')} disabled={busy} onPress={() => setCreating(false)} />
    </Card> : <Action title={t('Создать цель')} onPress={() => setCreating(true)} />)}
    {!contentId && <Action variant="outline" title={t('Прогресс')} onPress={() => router.navigate('/progress')} />}
    {message && <Action variant="outline" title={t('Обновить')} disabled={busy} onPress={refresh} />}
  </Page>;
}

export function GoalDetail({ request, id }: { request: Request; id: number }) {
  const t = useTranslation();
  const [offset, setOffset] = useState(0);
  const [picking, setPicking] = useState(false);
  const goalPath = `${path}/${id}` as const;
  const load = useCallback(async () => {
    const [goal, materials] = await Promise.all([
      request(goalPath, 'GET'),
      request(`${goalPath}/materials?limit=${limit}&offset=${offset}`, 'GET'),
    ]);
    return { goal: goal as Goal, materials: materials as ResultPage<GoalMaterial> };
  }, [goalPath, offset, request]);
  const { data, busy, message, refresh, save } = useGoalData(load);
  return <Page title={data?.goal.name ?? t('Цель')}>
    {message && <Notice>{message}</Notice>}
    {!data && !message && <Loading />}
    {data && <>
      <GoalEditor key={data.goal.version} goal={data.goal} busy={busy} onSave={(name, result, status) => {
        void save(() => request(goalPath, 'PUT', { name, result, status }, { version: data.goal.version }));
      }} />
      <GoalProgress goal={data.goal} />
      <Action variant="outline" title={t(picking ? 'Закрыть выбор материалов' : 'Добавить из библиотеки')} disabled={busy}
        onPress={() => setPicking(value => !value)} />
      {picking && <GoalPicker request={request} busy={busy} select={contentId => void save(
        () => request(`${goalPath}/materials`, 'POST', { content_id: contentId }),
        () => { setPicking(false); setOffset(0); },
      )} />}
      {data.materials.items.map(material => <Card key={material.id}>
        <Body>{material.title} · {t(statuses[material.status])}</Body>
        <Action variant="outline" title={t('Открыть материал')} onPress={() => router.push({
          pathname: '/library/[id]', params: { id: String(material.id) },
        })} />
        {data.goal.status === 'active' && material.status !== 'irrelevant' && <Action title={t('Запланировать материал')}
          onPress={() => router.push({ pathname: '/plan', params: { id: String(material.id), goalId: String(id) } })} />}
        <Action variant="text" title={t('Отвязать материал')} disabled={busy} onPress={() => void save(
          () => request(`${goalPath}/materials/${material.id}`, 'DELETE'),
          () => { if (offset > 0 && data.materials.items.length === 1) setOffset(offset - limit); },
        )} />
      </Card>)}
      <Steps offset={offset} total={data.materials.total} change={setOffset} disabled={busy} />
    </>}
    {message && <Action variant="outline" title={t('Обновить')} disabled={busy} onPress={refresh} />}
  </Page>;
}

function GoalEditor({ goal, onSave, busy }: {
  goal: Goal; onSave: (name: string, result: string | null, status: Status) => void; busy: boolean;
}) {
  const t = useTranslation();
  const [name, setName] = useState(goal.name);
  const [result, setResult] = useState(goal.result ?? '');
  const [editing, setEditing] = useState(false);
  const label = { active: 'Активная цель', completed: 'Завершённая цель', archived: 'Архивная цель' };
  const changeStatus = (status: Status) => onSave(goal.name, goal.result, status);
  return <Card>
    <Body>{t(label[goal.status])}</Body>
    {editing ? <>
      <GoalFields name={name} result={result} setName={setName} setResult={setResult} busy={busy} />
      <Action title={t('Сохранить цель')} disabled={busy || !name.trim() ||
        (name.trim() === goal.name && result.trim() === (goal.result ?? ''))}
        onPress={() => onSave(name.trim(), result.trim() || null, goal.status)} />
      <Action variant="text" title={t('Отмена')} disabled={busy} onPress={() => {
        setEditing(false); setName(goal.name); setResult(goal.result ?? '');
      }} />
    </> : <>
      {goal.result && <Body>{goal.result}</Body>}
      <Action variant="outline" title={t('Редактировать цель')} disabled={busy} onPress={() => setEditing(true)} />
      {goal.status === 'active' && <Action variant="outline" title={t('Завершить цель')} disabled={busy} onPress={() => changeStatus('completed')} />}
      {goal.status !== 'archived' && <Action variant="text" title={t('Архивировать цель')} disabled={busy} onPress={() => changeStatus('archived')} />}
      {goal.status !== 'active' && <Action variant="text" title={t('Вернуть в активные')} disabled={busy} onPress={() => changeStatus('active')} />}
    </>}
  </Card>;
}

function GoalPicker({ request, select, busy }: { request: Request; select: (id: number) => void; busy: boolean }) {
  const t = useTranslation();
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const load = useCallback(async () => await request(
    listPath({ ...initialFilters, q: query }, offset, limit), 'GET',
  ) as ResultPage<GoalMaterial>, [offset, query, request]);
  const { data, message, refresh } = useGoalData(load);
  return <Card>
    <Field label={t('Поиск по названию')} value={text} onChangeText={setText} maxLength={200} returnKeyType="search"
      onSubmitEditing={() => { setQuery(text.trim()); setOffset(0); }} />
    <Action variant="outline" title={t('Найти')} disabled={busy} onPress={() => { setQuery(text.trim()); setOffset(0); }} />
    {message && <><Notice>{message}</Notice><Action title={t('Обновить')} onPress={refresh} /></>}
    {!data && !message && <Loading />}
    {data?.items.length === 0 && <Body>{t('Материалы не найдены.')}</Body>}
    {data?.items.map(material => <Action key={material.id} variant="outline" title={material.title}
      disabled={busy} onPress={() => select(material.id)} />)}
    {data && <Steps offset={offset} total={data.total} change={setOffset} disabled={busy} />}
  </Card>;
}
