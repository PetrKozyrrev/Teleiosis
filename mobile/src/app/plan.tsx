import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Text } from 'react-native';
import { Action, Body, Card, Field, Page, styles } from '../components/ui';
import { Choice, LibraryAccess, Loading, Notice } from '../library/ui';
import { parseId, type Request } from '../library/model';
import { formatPlanDay, minutesValid, planError, priorities, type Task, type Week } from '../plan/model';
import { DatePicker, WeekNav } from '../plan/DatePicker';
import { useLocale, useTranslation } from '../i18n';

type Save = (operation: () => Promise<unknown>, after?: (result: unknown) => void) => Promise<void>;

export default function PlanRoute() {
  const { id, goalId } = useLocalSearchParams<{ id?: string; goalId?: string }>();
  return <LibraryAccess>{request => <Planner key={`${id ?? 'week'}:${goalId ?? ''}`} request={request}
    contentId={parseId(id)} preferredGoal={parseId(goalId)} />}</LibraryAccess>;
}

function Planner({ request, contentId, preferredGoal }: { request: Request; contentId: number | null; preferredGoal: number | null }) {
  const t = useTranslation();
  const locale = useLocale();
  const [anchor, setAnchor] = useState('');
  const [revision, setRevision] = useState(0);
  const [week, setWeek] = useState<Week>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const epoch = useRef(0);
  const locked = useRef(false);
  const [budgetExpanded, setBudgetExpanded] = useState(false);
  const [goalId, setGoalId] = useState(preferredGoal);
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
      setGoalId(previous => result.goals.find(goal => goal.id === previous)?.id ?? (preferredGoal ? null : result.goals[0]?.id ?? null));
      setDay(previous => previous || (anchor || result.today));
    }).catch(error => { if (current === epoch.current) setMessage(planError(error, true)); });
    return () => { epoch.current++; };
  }, [request, revision, anchor, contentId, preferredGoal]));

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
  const byDay = new Map<string, Task[]>();
  for (const task of week?.tasks ?? []) {
    const tasks = byDay.get(task.day);
    if (tasks) tasks.push(task);
    else byDay.set(task.day, [task]);
  }
  return <Page title={t('Недельный план')}>
    {message ? <Notice>{message}</Notice> : null}
    {week && summary ? <>
      <Card>
        <WeekNav week={week.week} disabled={busy} onChange={navigateWeek} />
        <Body>{week.budget === null ? t('Запланировано: {0} мин', summary.planned_minutes)
          : t('Запланировано: {0} из {1} мин', summary.planned_minutes, week.budget)}</Body>
        <Body>{t('Задания недели: выполнено {0} из {1}', summary.done, summary.total)}</Body>
        {week.budget !== null && summary.planned_minutes > week.budget &&
          <Body>{t('План превышает бюджет на {0} мин.', summary.planned_minutes - week.budget)}</Body>}
        <Action variant="text" title={t(budgetExpanded ? 'Скрыть настройки бюджета' : 'Настроить бюджет')}
          disabled={busy} onPress={() => setBudgetExpanded(!budgetExpanded)} />
        {budgetExpanded && <>
          <Body>{t('Оценка для выполненных заданий: {0} мин', summary.done_minutes)}</Body>
          <Field label={t('Бюджет недели в минутах')} value={budget} onChangeText={setBudget}
            keyboardType="number-pad" maxLength={5} editable={!disabled} />
          <Action variant="outline" title={t('Сохранить бюджет')} disabled={disabled || !minutesValid(budget, 10080) || Number(budget) === week.budget}
            onPress={() => void save(() => request(`/mobile/plan/weeks/${week.week}/budget`, 'PUT', { minutes: Number(budget), previous: week.budget }))} />
        </>}
      </Card>
      {contentId && !added ? <Card>
        <Text accessibilityRole="header" style={styles.heading}>{materialTitle}</Text>
        {week.goals.length > 0 && <Choice label={t('Цель')} value={goalId} onChange={setGoalId} disabled={disabled}
          options={week.goals.map(goal => ({ value: goal.id, label: goal.name }))} />}
        <Action variant="text" title={t('Перейти к целям')} disabled={busy} onPress={() => router.push('/goals')} />
        <DatePicker value={day || week.today} onChange={setDay} disabled={disabled} />
        <Field label={t('Длительность в минутах')} value={minutes} onChangeText={setMinutes} keyboardType="number-pad" maxLength={4} editable={!disabled} />
        <Choice label={t('Приоритет')} value={priority} options={priorities.map(option => ({ ...option, label: t(option.label) }))} onChange={setPriority} disabled={disabled} />
        <Action title={t('Запланировать материал')} disabled={disabled || !selected || !minutesValid(minutes, 1440)}
          onPress={() => void save(() => request('/mobile/plan/tasks', 'POST', { goal_id: goalId, content_id: contentId,
            day, minutes: Number(minutes), priority }), () => { setAdded(true); setAnchor(day); })} />
      </Card> : <Action variant={week.tasks.length ? 'outline' : 'primary'} title={t('Выбрать материал в библиотеке')}
        disabled={busy} onPress={() => router.dismissTo('/library')} />}
      {!byDay.size && <Body>{t('Пока нет заданий')}</Body>}
      {[...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, tasks]) => {
        const dateLabel = formatPlanDay(date, locale, { weekday: 'long', day: 'numeric', month: 'long' });
        return <DayTasks key={date} title={date === week.today ? t('Сегодня, {0}', dateLabel) : dateLabel}
          tasks={tasks} today={date === week.today} disabled={disabled} save={save} request={request} />;
      })}
    </> : !message && <Loading />}
    <Action variant="text" title={t('Обновить план')} disabled={busy} onPress={refresh} />
  </Page>;
}

function DayTasks({ title, tasks, today, disabled, save, request }: {
  title: string; tasks: Task[]; today: boolean; disabled: boolean; save: Save; request: Request;
}) {
  return <>
    <Text accessibilityRole="header" style={styles.heading}>{title}</Text>
    {tasks.map(task => <TaskRow key={task.id} task={task} today={today} disabled={disabled} save={save} request={request} />)}
  </>;
}

function TaskRow({ task, today, disabled, save, request }: {
  task: Task; today: boolean; disabled: boolean; save: Save; request: Request;
}) {
  const t = useTranslation();
  const locale = useLocale();
  const [day, setDay] = useState(task.day);
  const [actions, setActions] = useState(false);
  const path = `/mobile/plan/tasks/${task.id}` as const;
  const options = { version: task.version };
  const status = task.completed_at ? t('Выполнено') : t('Предстоит');
  return <Card featured={today && !task.completed_at}>
    <Text accessibilityRole="header" style={styles.label}>{task.title}</Text>
    <Body>{task.goal_name}</Body>
    <Body>{formatPlanDay(task.day, locale, { dateStyle: 'long' })} · {t('{0} мин', task.minutes)}</Body>
    <Body>{status} · {t(priorities.find(p => p.value === task.priority)?.label ?? '')} {t('приоритет')}</Body>
    <Action title={t('Открыть материал')} onPress={() => router.push({ pathname: '/library/[id]', params: {
      id: String(task.content_id), ...(!task.completed_at ? { taskId: String(task.id) } : {}),
    } })} />
    <Action variant="text" title={t(actions ? 'Скрыть действия' : 'Другие действия')} onPress={() => setActions(!actions)} />
    {actions && <>
      {!task.completed_at && <>
        <DatePicker value={day} onChange={setDay} disabled={disabled} />
        <Action variant="outline" title={t('Перенести задание')} disabled={disabled || day === task.day}
          onPress={() => void save(() => request(`${path}/day`, 'PUT', { day }, options))} />
        <Action variant="outline" title={t('Завершить задание')} disabled={disabled} onPress={() => Alert.alert(
          t('Завершить задание'), t('Задание будет выполнено. Статус материала сохранится.'), [
            { text: t('Отмена'), style: 'cancel' },
            { text: t('Завершить задание'), onPress: () => void save(() => request(`${path}/complete`, 'PUT', undefined, options)) },
          ],
        )} />
      </>}
      <Action variant="danger" title={t('Убрать задание')} disabled={disabled} onPress={() => Alert.alert(t('Убрать задание из плана?'), task.title,
        [{ text: t('Отмена'), style: 'cancel' }, { text: t('Убрать'), style: 'destructive', onPress: () => void save(() => request(path, 'DELETE', undefined, options)) }])} />
    </>}
  </Card>;
}
