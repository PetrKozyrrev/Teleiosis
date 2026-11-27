import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { AppState, Text } from 'react-native';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Page, styles } from '../components/ui';
import { useLocale, useTranslation } from '../i18n';
import { errorMessage, sources, type Request } from '../library/model';
import { Loading, Notice } from '../library/ui';
import { cachedSnapshot, readOnline, type Read } from '../offline/cache';
import { subscribe } from '../offline/store';
import { BudgetPresets } from './BudgetPresets';
import { trackLearning } from './events';

const path = '/mobile/learning/today';
const reasons = {
  overdue_task: 'Из плана на {0}',
  today_task: 'Задание на сегодня',
  studied_task: 'Задание по изученному материалу',
  planned_material: 'Запланировано в библиотеке',
  unseen_material: 'Следующий непросмотренный материал',
};

type NextAction = {
  material_id: number;
  task_id?: number | null;
  title: string;
  source: keyof typeof sources;
  content_type: string;
  reason: keyof typeof reasons;
  duration_minutes: number | null;
  task_day: string | null;
  goal_name?: string | null;
};

type TodayData = {
  local_date?: string;
  next_action?: NextAction | null;
  library_state?: 'available' | 'empty' | 'scheduled_later' | 'no_recommendation';
  due_review_count?: number | null;
  weekly_progress?: { weekly_goal: number; weekly_completed: number; tasks_total: number; tasks_done: number } | null;
};
type Result = { data: Read<TodayData> } | { error: unknown };

export function Today({ request, owner }: { request: Request; owner: string | null }) {
  const t = useTranslation();
  const locale = useLocale();
  const [response, setResponse] = useState<{ owner: string | null; result: Result }>();
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);

  useFocusEffect(useCallback(() => {
    const listener = AppState.addEventListener('change', state => { if (state === 'active') refresh(); });
    const unsubscribe = subscribe(synced => { if (synced) refresh(); });
    return () => { listener.remove(); unsubscribe(); };
  }, [refresh]));

  useFocusEffect(useCallback(() => {
    void revision;
    let active = true;
    const currentRequest: Request = async (...args) => {
      const value = await request(...args);
      if (!active) throw new ApiError(409);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ApiError(502);
      return value;
    };
    void readOnline<TodayData>(owner, currentRequest, path, key => cachedSnapshot(key, path))
      .then(data => {
        if (!active) return;
        setResponse({ owner, result: { data } });
        if (data.cachedAt === undefined) trackLearning(request, owner, { name: 'today_viewed' });
      })
      .catch(error => { if (active) setResponse({ owner, result: { error } }); });
    return () => { active = false; };
  }, [owner, request, revision]));

  const result = response?.owner === owner ? response?.result : undefined;
  const data = result && 'data' in result ? result.data : undefined;
  const error = result && 'error' in result ? result.error : undefined;
  const action = data?.value.next_action;
  const libraryState = data?.value.library_state;
  const due = data?.value.due_review_count;
  const progress = data?.value.weekly_progress;
  const date = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', timeZone: 'UTC' });
  const taskDate = action?.task_day ? date.format(new Date(action.task_day)) : null;
  const fromEarlierPlan = action?.reason === 'overdue_task'
    || (action?.task_day && data?.value.local_date && action.task_day < data.value.local_date);
  const add = () => router.navigate('/add-link');
  const openPlan = () => router.push('/plan');

  return <Page title={t('Сегодня')} headingAction={
    libraryState !== 'empty' && <Action variant="outline" title={t('Добавить')} onPress={add} />
  }>
    {!result && <Card><Loading /></Card>}
    {result && 'error' in result && <Card>
      <Notice>{error instanceof ApiError && error.status === 404
        ? t('На сервере пока недоступен экран «Сегодня».')
        : error instanceof ApiError && error.status === 0
          ? t('Нет связи с сервером. Данные экрана «Сегодня» недоступны.')
          : t(errorMessage(error))}</Notice>
      <Action variant="outline" title={t('Повторить')} onPress={refresh} />
    </Card>}
    {data && <>
      {data.cachedAt !== undefined && <Card>
        <Notice>{t('Данные могут быть устаревшими. Сохранено {0}.', new Intl.DateTimeFormat(locale, {
          dateStyle: 'short', timeStyle: 'short',
        }).format(data.cachedAt))}</Notice>
        <Action variant="outline" title={t('Обновить')} onPress={refresh} />
      </Card>}
      <Card featured={Boolean(action)}>
        <Text accessibilityRole="header" style={styles.label}>{t('Следующее занятие')}</Text>
        {action ? <>
          <Text accessibilityRole="header" style={styles.heading}>{action.title}</Text>
          <Body>{[t(action.content_type === 'pdf' ? 'PDF' : sources[action.source] ?? 'Источник неизвестен'),
            action.duration_minutes == null ? t('Время неизвестно') : t('≈ {0} мин', action.duration_minutes)].join(' · ')}</Body>
          {action.task_id && action.goal_name && <Body>{t('Цель: {0}', action.goal_name)}</Body>}
          <Body>{taskDate && (fromEarlierPlan || data.cachedAt !== undefined) ? t('Из плана на {0}', taskDate)
            : action.reason === 'overdue_task' ? t('Задание из плана') : t(reasons[action.reason])}</Body>
          {fromEarlierPlan && action.reason === 'studied_task' && <Body>{t(reasons.studied_task)}</Body>}
          <Action title={t('Открыть материал')} onPress={() => router.push({
            pathname: '/library/[id]', params: {
              id: String(action.material_id), ...(action.task_id ? { taskId: String(action.task_id) } : {}),
              ...(process.env.EXPO_PUBLIC_LEARNING_METRICS === '1' ? { learningEntry: 'today' } : {}),
            },
          })} />
          <Action variant="outline" title={t('Выбрать другое')} onPress={() => router.push('/time-budget')} />
        </> : <Body>{t(
          libraryState === 'empty' ? 'Сохраните первый материал, чтобы начать обучение.'
            : libraryState === 'scheduled_later' ? 'Следующее занятие запланировано на другой день.'
            : libraryState === 'no_recommendation' ? 'Можно выбрать материал в библиотеке или сохранить новый.'
            : 'Сведения о следующем занятии недоступны.',
        )}</Body>}
        {libraryState === 'empty' && <Action title={t('Добавить')} onPress={add} />}
        <Action variant="text" title={t('План')} onPress={openPlan} />
      </Card>
    </>}
    <Card>
      <Text accessibilityRole="header" style={styles.label}>{t('Сколько у вас времени?')}</Text>
      <BudgetPresets onSelect={value => router.push({ pathname: '/time-budget', params: { minutes: String(value) } })} />
    </Card>
    {result && <>
      <Card compact>
        <Text accessibilityRole="header" style={styles.label}>{t(due && due > 0 ? 'Пора повторить' : 'Повторение')}</Text>
        <Body>{due == null ? t('Количество доступных карточек неизвестно.')
          : due === 0 ? t('Пока нет карточек для повторения.') : t('Доступно карточек: {0}', due)}</Body>
        <Action variant="text" title={t('Повторение')} onPress={() => router.push({ pathname: '/review', params: { mode: 'session' } })} />
      </Card>
      <Card compact>
        <Text accessibilityRole="header" style={styles.label}>{t('Недельный прогресс')}</Text>
        {progress ? <>
          <Body>{t('Изучено {0} из {1} материалов', progress.weekly_completed, progress.weekly_goal)}</Body>
          {progress.tasks_total > 0 && <Body>{t('Задания недели: выполнено {0} из {1}', progress.tasks_done, progress.tasks_total)}</Body>}
        </> : <Body>{t('Недельный прогресс недоступен.')}</Body>}
        <Action variant="text" title={t('Прогресс')} onPress={() => router.navigate('/progress')} />
      </Card>
      {data && data.cachedAt === undefined && (action === undefined || due == null || !progress) &&
        <Action variant="outline" title={t('Обновить')} onPress={refresh} />}
    </>}
    {!data && <Action variant="text" title={t('План')} onPress={openPlan} />}
    <Action variant="text" title={t('Вся библиотека')} onPress={() => router.navigate('/library')} />
  </Page>;
}
