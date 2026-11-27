import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { AppState, Text } from 'react-native';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Page, styles } from '../components/ui';
import { useLocale, useTranslation } from '../i18n';
import { errorMessage, sources, statuses, type Request } from '../library/model';
import { Loading, Notice } from '../library/ui';
import { cachedSnapshot, readOnline, type Read } from '../offline/cache';
import { subscribe } from '../offline/store';
import { BudgetPresets } from './BudgetPresets';
import { trackLearning, type LearningBudget } from './events';

type Budget = LearningBudget;
const reasons = {
  overdue_task: 'Из плана на {0}',
  today_task: 'Задание на сегодня',
  active_goal: 'Материал активной цели',
  fits_time: 'Подходит по времени',
};

type Recommendation = {
  material_id: number;
  title: string;
  source: keyof typeof sources;
  content_type: string;
  status: 'unseen' | 'planned';
  duration_minutes: number;
  reason: keyof typeof reasons;
  context_goal_name?: string | null;
  task_id: number | null;
  task_day: string | null;
};
type BudgetData = {
  budget_minutes: Budget;
  local_date: string;
  items: Recommendation[];
  has_unknown_duration: boolean;
};
type Result = { data: Read<BudgetData> } | { error: unknown };

function errorText(error: unknown) {
  if (error instanceof ApiError && !error.gateway) {
    if (error.status === 0) return 'Нет связи с сервером. Сохранённого подбора на это время нет.';
    if (error.status === 404) return 'Подбор по времени пока недоступен на сервере.';
  }
  return errorMessage(error);
}

export function TimeBudget({ request, owner, initialBudget = null }: {
  request: Request; owner: string | null; initialBudget?: Budget | null;
}) {
  const t = useTranslation();
  const locale = useLocale();
  const [budget, setBudget] = useState<Budget | null>(initialBudget);
  const pendingSelection = useRef({ owner, budget: initialBudget });
  const [result, setResult] = useState<{ owner: string | null; budget: Budget; value: Result }>();
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);

  useFocusEffect(useCallback(() => {
    const foreground = AppState.addEventListener('change', state => { if (state === 'active') refresh(); });
    const unsubscribe = subscribe(synced => { if (synced) refresh(); });
    return () => { foreground.remove(); unsubscribe(); };
  }, [refresh]));

  useFocusEffect(useCallback(() => {
    void revision;
    if (budget === null) return;
    let active = true;
    const path = `/mobile/learning/time-budget?budget_minutes=${budget}` as const;
    const currentRequest: Request = async (...args) => {
      const response = await request(...args) as BudgetData;
      if (!active) throw new Error('Request ended');
      if (response?.budget_minutes !== budget || !Array.isArray(response.items)) throw new ApiError(502);
      return response;
    };
    void readOnline<BudgetData>(owner, currentRequest, path, key => cachedSnapshot(key, path))
      .then(data => {
        if (!active) return;
        setResult({ owner, budget, value: { data } });
        if (data.cachedAt === undefined && pendingSelection.current.owner === owner
          && pendingSelection.current.budget === budget) {
          pendingSelection.current = { owner, budget: null };
          trackLearning(request, owner, {
            name: 'time_budget_selected', budget_minutes: budget, has_results: data.value.items.length > 0,
          });
        }
      })
      .catch(error => { if (active) setResult({ owner, budget, value: { error } }); });
    return () => { active = false; };
  }, [budget, owner, request, revision]));

  const current = result?.budget === budget && result.owner === owner ? result.value : undefined;
  const data = current && 'data' in current ? current.data : undefined;
  const date = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', timeZone: 'UTC' });
  const openLibrary = () => router.dismissTo('/library');
  const [recommended, ...alternatives] = data?.value.items ?? [];

  function open(item: Recommendation) {
    router.push({
      pathname: '/library/[id]', params: {
        id: String(item.material_id), ...(item.task_id ? { taskId: String(item.task_id) } : {}),
        ...(process.env.EXPO_PUBLIC_LEARNING_METRICS === '1' ? { learningEntry: 'budget', learningBudget: String(budget) } : {}),
      },
    });
  }

  function details(item: Recommendation) {
    return <>
      <Body>{[t(statuses[item.status]), t(item.content_type === 'pdf' ? 'PDF' : sources[item.source] ?? 'Источник неизвестен'),
        t('≈ {0} мин', item.duration_minutes)].join(' · ')}</Body>
      <Body>{item.reason === 'overdue_task' || (item.task_day && data?.cachedAt !== undefined)
        ? item.task_day ? t('Из плана на {0}', date.format(new Date(item.task_day))) : t('Задание из плана')
        : t(reasons[item.reason])}</Body>
      {item.context_goal_name && <Body>{t('Цель: {0}', item.context_goal_name)}</Body>}
    </>;
  }

  return <Page title={t('Сколько у вас времени?')}>
    <Card>
      <BudgetPresets selected={budget} onSelect={value => {
        if (budget === value) return;
        pendingSelection.current = { owner, budget: value };
        setResult(undefined);
        setBudget(value);
      }} />
    </Card>
    {budget !== null && !current && <Card><Loading /></Card>}
    {current && 'error' in current && <Card>
      <Notice>{t(errorText(current.error))}</Notice>
      <Action variant="outline" title={t('Повторить')} onPress={refresh} />
    </Card>}
    {data && <>
      {data.cachedAt !== undefined && <Card>
        <Notice>{t('Данные могут быть устаревшими. Сохранено {0}.', new Intl.DateTimeFormat(locale, {
          dateStyle: 'short', timeStyle: 'short',
        }).format(data.cachedAt))}</Notice>
        <Action variant="outline" title={t('Обновить')} onPress={refresh} />
      </Card>}
      {data.value.items.length === 0 && <Card>
        <Body>{t('На это время подходящих материалов нет.')}</Body>
        {budget !== 60 && <Body>{t('Попробуйте выбрать больше времени.')}</Body>}
      </Card>}
      {recommended && <Card featured>
        <Text style={styles.label}>{t('Рекомендуемый материал')}</Text>
        <Text style={styles.heading} accessibilityRole="header">{recommended.title}</Text>
        {details(recommended)}
        <Action title={t('Открыть материал')} onPress={() => open(recommended)} />
      </Card>}
      {alternatives.length > 0 && <>
        <Text style={styles.label} accessibilityRole="header">{t('Другие варианты')}</Text>
        {alternatives.map(item => <Card compact key={item.material_id}>
          <Action variant="text" title={item.title} style={{ alignSelf: 'flex-start', maxWidth: '100%', paddingHorizontal: 0 }}
            accessibilityLabel={t('Открыть материал: {0}', item.title)} onPress={() => open(item)} />
          {details(item)}
        </Card>)}
      </>}
    </>}
    <Card compact>
      {data?.value.has_unknown_duration && <Body>{t('Есть материалы без оценки времени')}</Body>}
      <Action variant="text" title={t('Вся библиотека')} onPress={openLibrary} />
    </Card>
  </Page>;
}
