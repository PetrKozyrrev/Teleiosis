import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { AppState, Pressable, Text, View } from 'react-native';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Page, styles } from '../components/ui';
import { useLocale, useTranslation } from '../i18n';
import { errorMessage, sources, statuses, type Request } from '../library/model';
import { Loading, Notice } from '../library/ui';
import { cachedSnapshot, readOnline, type Read } from '../offline/cache';
import { subscribe } from '../offline/store';
import { trackLearning, type LearningBudget } from './events';

const budgets = [5, 15, 30, 60] as const;
type Budget = LearningBudget;
const reasons = {
  overdue_task: 'Просроченное задание',
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
  goal_name: string | null;
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

export function TimeBudget({ request, owner }: { request: Request; owner: string | null }) {
  const t = useTranslation();
  const locale = useLocale();
  const [budget, setBudget] = useState<Budget | null>(null);
  const pendingSelection = useRef<Budget | null>(null);
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
        if (data.cachedAt === undefined && pendingSelection.current === budget) {
          pendingSelection.current = null;
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
  const date = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' });
  const openLibrary = () => router.dismissTo('/library');
  return <Page title={t('Сколько у вас времени?')}>
    <Card>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {budgets.map(value => {
          const selected = budget === value;
          return <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected }}
            onPress={() => {
              if (selected) return;
              pendingSelection.current = value;
              setBudget(value);
            }}
            style={[styles.button, !selected && styles.outline, { flexGrow: 1, flexBasis: '40%' }]}>
            <Text style={[styles.buttonText, !selected && styles.label]}>{t('{0} мин', value)}</Text>
          </Pressable>;
        })}
      </View>
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
      {data.value.items.map(item => <Card key={item.material_id}>
        <Text style={styles.label} accessibilityRole="header">{item.title}</Text>
        <Body>{[t(statuses[item.status]), t(item.content_type === 'pdf' ? 'PDF' : sources[item.source] ?? 'Источник неизвестен'),
          t('≈ {0} мин', item.duration_minutes)].join(' · ')}</Body>
        <Body>{[t(reasons[item.reason]), item.task_day ? date.format(new Date(item.task_day)) : null].filter(Boolean).join(' · ')}</Body>
        {item.goal_name && <Body>{t('Цель: {0}', item.goal_name)}</Body>}
        <Action variant="outline" title={t('Открыть материал')} onPress={() => router.push({
          pathname: '/library/[id]', params: {
            id: String(item.material_id), ...(item.task_id ? { taskId: String(item.task_id) } : {}),
            ...(process.env.EXPO_PUBLIC_LEARNING_METRICS === '1' ? { learningEntry: 'budget', learningBudget: String(budget) } : {}),
          },
        })} />
      </Card>)}
      {data.value.has_unknown_duration && <Notice>{t('Есть материалы без оценки времени')}</Notice>}
    </>}
    <Action variant="outline" title={t('Вся библиотека')} onPress={openLibrary} />
  </Page>;
}
