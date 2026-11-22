import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert } from 'react-native';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { Choice, LibraryAccess, Loading, Notice } from '../library/ui';
import { parseId, type Request } from '../library/model';
import { minutesValid, planError, priorities, shiftDay, validDay, type Task, type Week } from '../plan/model';

type Save = (operation: () => Promise<unknown>, after?: (result: unknown) => void) => Promise<void>;

export default function PlanRoute() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  return <LibraryAccess>{request => <Planner key={id ?? 'week'} request={request} contentId={parseId(id)} />}</LibraryAccess>;
}

function Planner({ request, contentId }: { request: Request; contentId: number | null }) {
  const [anchor, setAnchor] = useState('');
  const [revision, setRevision] = useState(0);
  const [week, setWeek] = useState<Week>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const epoch = useRef(0);
  const locked = useRef(false);
  const [goalName, setGoalName] = useState('');
  const [goalId, setGoalId] = useState<number | null>(null);
  const [day, setDay] = useState('');
  const [minutes, setMinutes] = useState('');
  const [priority, setPriority] = useState(2);
  const [budget, setBudget] = useState('');
  const [added, setAdded] = useState(false);
  const [materialTitle, setMaterialTitle] = useState('');
  useFocusEffect(useCallback(() => {
    void revision;
    const current = ++epoch.current;
    setWeek(undefined); setStale(false); setBusy(false); locked.current = false;
    void Promise.all([
      request(anchor ? `/mobile/plan?day=${anchor}` : '/mobile/plan', 'GET'),
      contentId ? request(`/contents/${contentId}`, 'GET') : Promise.resolve(null),
    ]).then(([response, material]) => {
      if (current !== epoch.current) return;
      const result = response as Week;
      setWeek(result);
      setMaterialTitle((material as { title: string } | null)?.title ?? '');
      setBudget(result.budget?.toString() ?? '');
      setGoalId(previous => result.goals.find(goal => goal.id === previous)?.id ?? result.goals[0]?.id ?? null);
      setDay(previous => previous || (anchor || result.today));
    }).catch(error => { if (current === epoch.current) setMessage(planError(error, true)); });
    return () => { epoch.current++; };
  }, [request, revision, anchor, contentId]));

  function refresh() {
    setMessage(''); setWeek(undefined); setRevision(value => value + 1);
  }
  function navigateWeek(next: string) {
    setMessage(''); setDay(''); setWeek(undefined); setAnchor(next);
  }
  const save: Save = async (operation, after) => {
    if (locked.current || stale || !week) return;
    const current = epoch.current;
    locked.current = true; setBusy(true); setMessage('');
    try {
      const value = await operation();
      if (current !== epoch.current) return;
      after?.(value);
      setWeek(undefined); setRevision(value => value + 1); setMessage('Сохранено.');
    } catch (error) {
      if (current === epoch.current) { setMessage(planError(error)); setStale(true); }
    } finally {
      if (current === epoch.current) { locked.current = false; setBusy(false); }
    }
  };
  const disabled = busy || stale;
  const selected = week?.goals.find(goal => goal.id === goalId);
  const summary = week?.summary;
  const next = week?.tasks.find(task => task.id === summary?.next_id);
  return <Page title="Недельный план">
    {message ? <Notice>{message}</Notice> : null}
    {week && summary ? <>
      <Card><Body>{week.week} — {week.end}</Body>
        <Body>{summary.total ? `Выполнено ${summary.done} из ${summary.total} · ${Math.round(summary.done * 100 / summary.total)} %` : 'Пока нет заданий'}</Body>
        <Body>По плану {summary.planned_minutes} мин · выполнено на {summary.done_minutes} мин</Body>
        {week.budget !== null && <Body>Бюджет недели · {week.budget} мин</Body>}
        {week.budget !== null && summary.planned_minutes > week.budget && <Body>План превышает бюджет на {summary.planned_minutes - week.budget} мин. Перенесите часть заданий.</Body>}
        {next && <Body>Следующее по приоритету · {next.title} · {next.day}</Body>}
        <Action title="Предыдущая неделя" disabled={busy || !validDay(shiftDay(week.week, -7))} onPress={() => navigateWeek(shiftDay(week.week, -7))} />
        <Action title="Следующая неделя" disabled={busy || !validDay(shiftDay(week.week, 7))} onPress={() => navigateWeek(shiftDay(week.week, 7))} />
      </Card>
      <Card><Field label="Бюджет недели в минутах" value={budget} onChangeText={setBudget} keyboardType="number-pad" maxLength={5} />
        <Action title="Сохранить бюджет" disabled={disabled || !minutesValid(budget, 10080) || Number(budget) === week.budget}
          onPress={() => void save(() => request(`/mobile/plan/weeks/${week.week}/budget`, 'PUT', { minutes: Number(budget), previous: week.budget }))} />
      </Card>
      <Card><Field label="Название новой цели" value={goalName} maxLength={100} onChangeText={setGoalName} />
        <Action title="Создать цель" disabled={disabled || !goalName.trim()} onPress={() => void save(
          () => request('/mobile/plan/goals', 'POST', { name: goalName.trim() }),
          goal => { setGoalId((goal as { id: number }).id); setGoalName(''); })} />
        {week.goals.length > 0 && <Choice label="Цель" value={goalId} onChange={setGoalId} disabled={disabled}
          options={week.goals.map(goal => ({ value: goal.id, label: goal.name }))} />}
        {selected && <Action title="Удалить выбранную цель" disabled={disabled} onPress={() => Alert.alert(
          `Удалить «${selected.name}»?`, 'Задания этой цели за все недели будут удалены. Материалы останутся в библиотеке.',
          [{ text: 'Отмена', style: 'cancel' }, { text: 'Удалить', style: 'destructive',
            onPress: () => void save(() => request(`/mobile/plan/goals/${selected.id}`, 'DELETE')) }])} />}
      </Card>
      {contentId && !added ? <Card><Body>{materialTitle}</Body>
        <Field label="Дата задания (ГГГГ-ММ-ДД)" value={day} onChangeText={setDay} maxLength={10} />
        <Field label="Длительность в минутах" value={minutes} onChangeText={setMinutes} keyboardType="number-pad" maxLength={4} />
        <Choice label="Приоритет" value={priority} options={priorities} onChange={setPriority} disabled={disabled} />
        <Action title="Запланировать материал" disabled={disabled || !selected || !validDay(day) || !minutesValid(minutes, 1440)}
          onPress={() => void save(() => request('/mobile/plan/tasks', 'POST', { goal_id: goalId, content_id: contentId,
            day, minutes: Number(minutes), priority }), () => { setAdded(true); setAnchor(day); })} />
      </Card> : <Action title="Выбрать материал в библиотеке" disabled={busy} onPress={() => router.dismissTo('/')} />}
      {week.tasks.map(task => <TaskRow key={task.id} task={task} disabled={disabled} save={save} request={request} />)}
    </> : !message && <Loading />}
    <Action title="Обновить план" disabled={busy} onPress={refresh} />
  </Page>;
}

function TaskRow({ task, disabled, save, request }: { task: Task; disabled: boolean; save: Save; request: Request }) {
  const [day, setDay] = useState(task.day);
  const path = `/mobile/plan/tasks/${task.id}` as const;
  const options = { version: task.version };
  return <Card><Body>{task.title} · {task.goal_name}</Body>
    <Body>{task.day} · {task.minutes} мин · {priorities.find(p => p.value === task.priority)?.label} приоритет</Body>
    {task.completed_at ? <Body>Выполнено</Body> : <>
      <Action title="Завершить задание" disabled={disabled} onPress={() => void save(() => request(`${path}/complete`, 'PUT', undefined, options))} />
      <Field label="Перенести на дату (ГГГГ-ММ-ДД)" value={day} onChangeText={setDay} maxLength={10} />
      <Action title="Перенести задание" disabled={disabled || day === task.day || !validDay(day)}
        onPress={() => void save(() => request(`${path}/day`, 'PUT', { day }, options))} />
    </>}
    <Action title="Открыть материал" onPress={() => router.push({ pathname: '/library/[id]', params: { id: String(task.content_id) } })} />
    <Action title="Убрать задание" disabled={disabled} onPress={() => Alert.alert('Убрать задание из плана?', task.title,
      [{ text: 'Отмена', style: 'cancel' }, { text: 'Убрать', style: 'destructive', onPress: () => void save(() => request(path, 'DELETE', undefined, options)) }])} />
  </Card>;
}
