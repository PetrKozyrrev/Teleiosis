import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Field, Page, styles } from '../components/ui';
import { useTranslation } from '../i18n';
import { errorMessage, statuses, type Material, type Request } from '../library/model';
import { Choice, Loading, Notice } from '../library/ui';
import { colors } from '../theme';

const path = '/mobile/learning/goals';
const limit = 20;
const goalStatuses = { active: 'Активные', completed: 'Завершённые', archived: 'Архивные' };
type Status = keyof typeof goalStatuses;
type Goal = {
  id: number; name: string; result: string | null; status: Status; version: number;
  materials_total: number; materials_studied: number; linked?: boolean;
};
type GoalMaterial = Pick<Material, 'id' | 'title' | 'status'>;
type Candidate = GoalMaterial & { linked: boolean; duration_minutes: number | null; content_type: string };
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

function candidateError(error: unknown) {
  if (error instanceof ApiError && !error.gateway && error.status === 404) {
    return 'Цель недоступна или сервер пока не поддерживает выбор нескольких материалов.';
  }
  return goalError(error);
}

function useGoalData<T>(load: () => Promise<T>, readError = goalError) {
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
      .catch(error => { if (current === epoch.current) setMessage(readError(error)); });
    return () => { epoch.current++; };
  }, [load, readError, revision]));

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
  if (!goal.materials_total) return <Body>{t('Добавьте материалы')}</Body>;
  const label = t('Изучено {0} из {1} материалов', goal.materials_studied, goal.materials_total);
  return <View style={goalStyles.progress} accessible accessibilityRole="progressbar" accessibilityLabel={label}
    accessibilityValue={{ min: 0, max: goal.materials_total, now: goal.materials_studied }}>
    <Body>{label}</Body>
    <View style={goalStyles.track}><View style={[goalStyles.fill,
      { width: `${Math.min(100, goal.materials_studied * 100 / goal.materials_total)}%` }]} /></View>
  </View>;
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
  const openGoal = (id: number) => router.push({ pathname: '/goals/[id]', params: { id: String(id) } });
  return <Page title={t(contentId ? 'Добавить к цели' : 'Цели')} headingAction={!contentId && !creating
    && <Action title={t('Создать цель')} onPress={() => setCreating(true)} />}>
    {creating && <Card>
      <GoalFields name={name} result={result} setName={setName} setResult={setResult} busy={busy} />
      <Action title={t('Создать цель')} disabled={busy || !name.trim()} onPress={() => void save(
        () => request(path, 'POST', { name: name.trim(), result: result.trim() || null }),
        value => { setCreating(false); setName(''); setResult(''); openGoal((value as Goal).id); },
      )} />
      <Action variant="text" title={t('Отмена')} disabled={busy} onPress={() => setCreating(false)} />
    </Card>}
    <Choice label={t('Статус целей')} options={(Object.keys(goalStatuses) as Status[]).map(value => ({
      value, label: t(goalStatuses[value]),
    }))} value={status} disabled={busy} onChange={value => { setStatus(value); setOffset(0); }} />
    {message && <Notice>{message}</Notice>}
    {!data && !message && <Loading />}
    {data && <>
      {!data.items.length && <Body>{t('В этом списке пока нет целей.')}</Body>}
      {data.items.map(goal => <Card key={goal.id} onPress={contentId ? undefined : () => openGoal(goal.id)}>
        <Text style={styles.heading}>{goal.name}</Text>
        {goal.result && <Body>{goal.result}</Body>}
        <GoalProgress goal={goal} />
        {contentId && <>
          {goal.linked && <Body>{t('Материал уже связан с целью.')}</Body>}
          <Action variant="outline" title={t(goal.linked ? 'Отвязать материал' : 'Привязать материал')} disabled={busy}
            onPress={() => void save(() => goal.linked
              ? request(`${path}/${goal.id}/materials/${contentId}`, 'DELETE')
              : request(`${path}/${goal.id}/materials`, 'POST', { content_id: contentId }))} />
        </>}
      </Card>)}
      <Steps offset={offset} total={data.total} change={setOffset} disabled={busy} />
    </>}
    {!contentId && <Action variant="outline" title={t('Прогресс')} onPress={() => router.navigate('/progress')} />}
    {message && <Action variant="outline" title={t('Обновить')} disabled={busy} onPress={refresh} />}
  </Page>;
}

export function GoalDetail({ request, id }: { request: Request; id: number }) {
  const t = useTranslation();
  const [offset, setOffset] = useState(0);
  const goalPath = `${path}/${id}` as const;
  const load = useCallback(async () => {
    const [goal, materials] = await Promise.all([
      request(goalPath, 'GET'),
      request(`${goalPath}/materials?limit=${limit}&offset=${offset}`, 'GET'),
    ]);
    return { goal: goal as Goal & { next_material?: GoalMaterial | null }, materials: materials as ResultPage<GoalMaterial> };
  }, [goalPath, offset, request]);
  const { data, busy, message, refresh, save } = useGoalData(load);
  const open = (material: GoalMaterial) => router.push({
    pathname: '/library/[id]', params: { id: String(material.id) },
  });
  const next = data?.goal.next_material;
  return <Page title={data?.goal.name ?? t('Цель')}>
    {message && <Notice>{message}</Notice>}
    {!data && !message && <Loading />}
    {data && <>
      <Card>
        {data.goal.result && <Body>{data.goal.result}</Body>}
        <GoalProgress goal={data.goal} />
      </Card>
      {next && data.goal.status === 'active' && <Card featured>
        <Text style={styles.label}>{t('Материал для изучения')}</Text>
        <Text style={styles.heading}>{next.title}</Text>
        <Action title={t('Открыть материал')} onPress={() => open(next)} />
      </Card>}
      <Action variant={next && data.goal.status === 'active' ? 'outline' : 'primary'}
        title={t('Добавить из библиотеки')} disabled={busy}
        onPress={() => router.push({ pathname: '/goals/materials', params: { goalId: String(id) } })} />
      <Text accessibilityRole="header" style={styles.label}>{t('Связанные материалы')}</Text>
      {data.materials.items.map(material => <Card key={material.id}>
        <Body>{material.title} · {t(statuses[material.status])}</Body>
        <Action variant="text" title={t('Открыть материал')} onPress={() => open(material)} />
        {data.goal.status === 'active' && material.status !== 'irrelevant' && <Action variant="outline" title={t('Запланировать материал')}
          onPress={() => router.push({ pathname: '/plan', params: { id: String(material.id), goalId: String(id) } })} />}
        <Action variant="text" title={t('Отвязать материал')} disabled={busy} onPress={() => void save(
          () => request(`${goalPath}/materials/${material.id}`, 'DELETE'),
          () => { if (offset > 0 && data.materials.items.length === 1) setOffset(offset - limit); },
        )} />
      </Card>)}
      <Steps offset={offset} total={data.materials.total} change={setOffset} disabled={busy} />
      <GoalEditor key={data.goal.version} goal={data.goal} busy={busy} onSave={(name, result, status) => {
        void save(() => request(goalPath, 'PUT', { name, result, status }, { version: data.goal.version }));
      }} />
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
  function changeStatus(status: Status, title: string) {
    Alert.alert(t(title), goal.name, [
      { text: t('Отмена'), style: 'cancel' },
      { text: t(title), onPress: () => onSave(goal.name, goal.result, status) },
    ]);
  }
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
      <Action variant="outline" title={t('Редактировать цель')} disabled={busy} onPress={() => setEditing(true)} />
      {goal.status === 'active' && <Action variant="outline" title={t('Завершить цель')} disabled={busy}
        onPress={() => changeStatus('completed', 'Завершить цель')} />}
      {goal.status !== 'archived' && <Action variant="text" title={t('Архивировать цель')} disabled={busy}
        onPress={() => changeStatus('archived', 'Архивировать цель')} />}
      {goal.status !== 'active' && <Action variant="text" title={t('Вернуть в активные')} disabled={busy}
        onPress={() => changeStatus('active', 'Вернуть в активные')} />}
    </>}
  </Card>;
}

const candidateTypes: Record<string, string> = {
  article: 'Статья', video: 'Видео', note: 'Заметка', pdf: 'PDF', other: 'Материал',
};

export function GoalPicker({ request, id }: { request: Request; id: number }) {
  const t = useTranslation();
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number[]>([]);
  const [added, setAdded] = useState<number[]>([]);
  const [sending, setSending] = useState(false);
  const [outcome, setOutcome] = useState<{ added: number; remaining: number }>();
  const sendingLock = useRef(false);
  const lifetime = useRef(0);
  useEffect(() => () => { lifetime.current++; }, []);
  const goalPath = `/mobile/learning/goals/${id}` as const;
  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset), q: query });
    return await request(`${goalPath}/candidates?${params}`, 'GET') as ResultPage<Candidate>;
  }, [goalPath, offset, query, request]);
  const { data, message, refresh } = useGoalData(load, candidateError);
  const linked = new Set([...added, ...(data?.items.filter(item => item.linked).map(item => item.id) ?? [])]);
  const pending = selected.filter(item => !linked.has(item));

  async function addSelected() {
    if (sendingLock.current || pending.length === 0) return;
    sendingLock.current = true;
    const current = lifetime.current;
    setSending(true);
    const confirmed: number[] = [];
    for (const content_id of pending) {
      if (lifetime.current !== current) return;
      try {
        await request(`${goalPath}/materials`, 'POST', { content_id });
        confirmed.push(content_id);
      } catch (error) {
        if (error instanceof ApiError && (error.status === 0 || error.status === 401)) break;
      }
    }
    if (lifetime.current !== current) return;
    const successful = new Set(confirmed);
    setAdded(previous => [...previous, ...confirmed]);
    setSelected(pending.filter(value => !successful.has(value)));
    setOutcome({ added: confirmed.length, remaining: pending.length - confirmed.length });
    setSending(false);
    sendingLock.current = false;
  }

  function search() {
    setQuery(text.trim());
    setOffset(0);
  }

  return <Page title={t('Добавить из библиотеки')} insetFooter footer={<>
    <Body>{t('Выбрано: {0}', pending.length)}</Body>
    {outcome && <Notice>{t('Добавлено: {0}. Осталось добавить: {1}.', outcome.added, outcome.remaining)}</Notice>}
    <Action title={t(sending ? 'Сохранение…' : outcome?.remaining ? 'Повторить добавление' : 'Добавить выбранные')}
      disabled={sending || !pending.length} onPress={() => void addSelected()} />
    <Action variant="text" title={t('Готово')} disabled={sending} onPress={() => router.back()} />
  </>}>
    <Field label={t('Поиск по названию')} value={text} onChangeText={setText} maxLength={100} returnKeyType="search"
      editable={!sending} onSubmitEditing={search} />
    <Action variant="outline" title={t('Найти')} disabled={sending} onPress={search} />
    {message && <><Notice>{message}</Notice><Action variant="outline" title={t('Обновить')} onPress={refresh} /></>}
    {!data && !message && <Loading />}
    {data?.items.length === 0 && <Body>{t('Материалы не найдены.')}</Body>}
    {data?.items.map(material => {
      const alreadyLinked = linked.has(material.id);
      const checked = alreadyLinked || pending.includes(material.id);
      const details = [t(candidateTypes[material.content_type] ?? 'Материал'), t(statuses[material.status]),
        material.duration_minutes ? t('≈ {0} мин', material.duration_minutes) : t('Время неизвестно')].join(' · ');
      return <Pressable key={material.id} accessibilityRole="checkbox"
        accessibilityLabel={[material.title, details, alreadyLinked ? t('Материал уже связан с целью.') : null].filter(Boolean).join('. ')}
        accessibilityState={{ checked, disabled: sending || alreadyLinked }} disabled={sending || alreadyLinked}
        style={goalStyles.candidate} onPress={() => {
          setOutcome(undefined);
          setSelected(previous => checked ? previous.filter(value => value !== material.id) : [...previous, material.id]);
        }}>
        <Ionicons name={checked ? 'checkbox' : 'square-outline'} size={24} color={colors.primary} />
        <View style={goalStyles.details}>
          <Text style={styles.label}>{material.title}</Text>
          <Body>{details}</Body>
          {alreadyLinked && <Body>{t('Материал уже связан с целью.')}</Body>}
        </View>
      </Pressable>;
    })}
    {data && <Steps offset={offset} total={data.total} change={setOffset} disabled={sending} />}
  </Page>;
}

const goalStyles = StyleSheet.create({
  progress: { gap: 6 },
  track: { height: 5, borderRadius: 3, backgroundColor: colors.coolTint, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: colors.primary },
  candidate: { flexDirection: 'row', alignItems: 'center', minHeight: 48, gap: 12, padding: 12,
    backgroundColor: colors.surface, borderRadius: 12 },
  details: { flex: 1, gap: 3 },
});
