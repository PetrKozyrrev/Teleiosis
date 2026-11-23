import { useCallback, useState } from 'react';
import { router, useFocusEffect } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { ApiError } from '../../auth/api';
import { Action, Body, Card, Page, styles } from '../../components/ui';
import { LibraryAccess, Loading, Notice } from '../../library/ui';
import { MaterialThumbnail } from '../../library/MaterialThumbnail';
import { errorMessage, linkDomain, statuses, type Material, type Request } from '../../library/model';
import { shiftDay } from '../../plan/model';
import { colors } from '../../theme';

const periods = { week: 'Эта неделя', month: 'Этот месяц', all: 'Всё время' } as const;
type Period = keyof typeof periods;
type Finished = Pick<Material, 'id' | 'title' | 'url' | 'content_type' | 'image_url'> & { local_day: string };
type ProgressData = {
  today: string; weekly_goal: number; weekly_completed: number; completed: number; streak: number;
  activity: { day: string; count: number }[]; recent: Finished[]; next_offset: number | null;
};

export default function Progress() {
  return <LibraryAccess title="Прогресс" brand>{request => <ProgressView request={request} />}</LibraryAccess>;
}

function ProgressView({ request }: { request: Request }) {
  const [period, setPeriod] = useState<Period>('week');
  const [result, setResult] = useState<{ period: Period; offset: number; value: ProgressData }>();
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [legacy, setLegacy] = useState(false);
  const [offset, setOffset] = useState(0);
  const data = result?.period === period ? result.value : undefined;
  const loadingMore = Boolean(data && result?.offset !== offset && !message);

  useFocusEffect(useCallback(() => () => {
    setOffset(0);
    setExpanded(false);
  }, []));

  useFocusEffect(useCallback(() => {
    void revision;
    let active = true;
    setMessage('');
    void request(`/mobile/reading-progress?period=${period}&offset=${offset}`, 'GET').then(value => {
      if (!active) return;
      setLegacy(false);
      const next = value as ProgressData;
      setResult(previous => ({ period, offset, value: offset > 0 && previous?.period === period && previous.offset < offset
        ? { ...next, recent: [...previous.value.recent, ...next.recent.filter(item => !previous.value.recent.some(existing => existing.id === item.id))] }
        : next }));
    }).catch(error => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 404 && !error.gateway) {
        setLegacy(true);
        setMessage('Недельная цель и выбор периода появятся после обновления сервера.');
      } else setMessage(errorMessage(error));
    });
    return () => { active = false; };
  }, [offset, period, request, revision]));

  const recent = data?.recent.slice(0, expanded ? undefined : 2) ?? [];
  return <Page brand title="Прогресс" subtitle="Маленькие шаги к тому, что важно.">
    {!legacy && <View style={screenStyles.periods}>
      {(Object.keys(periods) as Period[]).map(value => <Pressable key={value} accessibilityRole="button"
        accessibilityState={{ selected: period === value }} onPress={() => { setPeriod(value); setOffset(0); setExpanded(false); }}
        style={[screenStyles.period, period === value && screenStyles.selected]}>
        <Text style={[styles.label, period === value && screenStyles.selectedText]}>{periods[value]}</Text>
      </Pressable>)}
    </View>}
    {data && <>
      <Card>
        <Text style={styles.label}>{period === 'week' ? 'Недельная цель' : 'Изучено за период'}</Text>
        <View style={screenStyles.stat}>
          <Text style={screenStyles.count}>{period === 'week' ? `${data.weekly_completed} из ${data.weekly_goal}` : data.completed}</Text>
          <Body>материалов</Body>
        </View>
        {period === 'week' && <>
          <View accessibilityRole="progressbar" accessibilityLabel="Недельная цель"
            accessibilityValue={{ min: 0, max: data.weekly_goal, now: Math.min(data.weekly_goal, data.weekly_completed) }} style={screenStyles.track}>
            <View style={[screenStyles.fill, { width: `${Math.min(100, data.weekly_completed / data.weekly_goal * 100)}%` }]} />
          </View>
          <Body>{data.weekly_completed >= data.weekly_goal ? 'Цель недели достигнута.' : `До цели осталось: ${data.weekly_goal - data.weekly_completed}.`}</Body>
        </>}
      </Card>
      <Card>
        <Text style={styles.label}>Активность</Text>
        <View style={screenStyles.between}>
          <Body>{period === 'all' ? 'До 12 месяцев с активностью' : periods[period]}</Body>
          {data.streak > 0 && <Text style={[styles.label, styles.link]}>Дней подряд: {data.streak}</Text>}
        </View>
        <Activity data={data} period={period} />
      </Card>
      <View style={screenStyles.between}>
        <Text style={styles.label}>Недавно изучено</Text>
        {data.recent.length > 2 && <Action variant="text" title={expanded ? 'Свернуть' : 'Все материалы'} onPress={() => setExpanded(!expanded)} />}
      </View>
      {recent.length === 0 && <Body>В этом периоде пока нет изученных материалов.</Body>}
      {recent.map(item => <Pressable key={item.id} accessibilityRole="button" style={screenStyles.material}
        onPress={() => router.push({ pathname: '/library/[id]', params: { id: String(item.id) } })}>
        <MaterialThumbnail size={48} imageUrl={item.image_url} kind={item.content_type} />
        <View style={screenStyles.details}>
          <Text style={styles.label}>{item.title}</Text>
          <Body>{[linkDomain(item.url), relativeDay(item.local_day, data.today)].filter(Boolean).join(' · ')}</Body>
        </View>
        <Ionicons name="checkmark-circle" color={colors.success} size={20} />
      </Pressable>)}
      {expanded && data.next_offset !== null && <Action variant="outline" title="Показать ещё" disabled={loadingMore}
        onPress={() => { if (data.next_offset !== null) setOffset(data.next_offset); }} />}
    </>}
    {!data && !message && <Loading />}
    {message && <><Notice>{message}</Notice><Action variant="outline" title="Обновить прогресс" onPress={() => setRevision(value => value + 1)} /></>}
    <Action variant="outline" title="Недельный план" onPress={() => router.push('/plan')} />
    <Action variant="outline" title="Повторить карточки" onPress={() => router.push('/review')} />
    {!legacy && <Action variant="text" title={showDetails ? 'Скрыть статистику библиотеки' : 'Статистика библиотеки'}
      onPress={() => setShowDetails(!showDetails)} />}
    {(legacy || showDetails) && <LibraryStats request={request} />}
  </Page>;
}

type Stats = {
  total: number; by_status: Record<keyof typeof statuses, number>;
  studied_share: number | null; return_share: number | null;
  added_7d: number; studied_7d: number; top_categories: { id: number; name: string; count: number }[];
};

function LibraryStats({ request }: { request: Request }) {
  const [stats, setStats] = useState<Stats>();
  const [error, setError] = useState('');
  useFocusEffect(useCallback(() => {
    let active = true;
    setError('');
    void request('/stats', 'GET').then(value => { if (active) setStats(value as Stats); })
      .catch(reason => { if (active) setError(errorMessage(reason)); });
    return () => { active = false; };
  }, [request]));
  if (error) return <Notice>{error}</Notice>;
  if (!stats) return <Loading />;
  const percent = (value: number | null) => value === null ? 'Пока нет данных' : `${Math.round(value * 100)} %`;
  return <Card>
    <Text style={styles.label}>Материалов: {stats.total}</Text>
    {Object.entries(statuses).map(([key, label]) => <Body key={key}>{label} · {stats.by_status[key as keyof typeof statuses]}</Body>)}
    <Body>Доля изученного · {percent(stats.studied_share)}</Body>
    <Body>Возврат к оригиналу · {percent(stats.return_share)}</Body>
    <Body>За последние семь дней добавлено {stats.added_7d}, изучено {stats.studied_7d}.</Body>
    {stats.top_categories.map(category => <Body key={category.id}>{category.name} · {category.count}</Body>)}
  </Card>;
}

function relativeDay(day: string, today: string) {
  if (day === today) return 'Сегодня';
  if (day === shiftDay(today, -1)) return 'Вчера';
  return new Date(`${day}T00:00:00Z`).toLocaleDateString('ru-RU', { timeZone: 'UTC' });
}

const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
function Activity({ data, period }: { data: ProgressData; period: Period }) {
  if (!data.activity.length) return <Body>Пока нет активности.</Body>;
  const max = Math.max(1, ...data.activity.map(point => point.count));
  const formatter = new Intl.DateTimeFormat('ru-RU', { month: 'short', timeZone: 'UTC' });
  return <View style={screenStyles.chart}>
    {data.activity.map((point, index) => {
      const label = period === 'week' ? weekdays[index] : period === 'month' ? point.day.slice(-2)
        : formatter.format(new Date(`${point.day}T00:00:00Z`));
      const showLabel = period === 'week' || (period === 'month' ? index % 5 === 0 : index % 2 === 0);
      return <View key={point.day} accessible accessibilityLabel={`${point.day}, изучено: ${point.count}`} style={screenStyles.barColumn}>
        <View style={[screenStyles.bar, { height: Math.max(3, (point.count / max) * 64),
          backgroundColor: point.day === data.today ? colors.primary : point.count ? colors.secondary : colors.coolTint }]} />
        <Text style={screenStyles.barLabel} numberOfLines={1}>{showLabel ? label : ' '}</Text>
      </View>;
    })}
  </View>;
}

const screenStyles = StyleSheet.create({
  periods: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  period: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 22, backgroundColor: colors.surface },
  selected: { backgroundColor: colors.text },
  selectedText: { color: colors.surface },
  stat: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'baseline' },
  count: { ...styles.heading, fontSize: 29 },
  track: { height: 8, backgroundColor: colors.greenTint, borderRadius: 5 },
  fill: { height: '100%', borderRadius: 5, backgroundColor: colors.success },
  between: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' },
  chart: { minHeight: 92, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', gap: 2 },
  barColumn: { flex: 1, alignItems: 'center', gap: 5 },
  bar: { width: '68%', maxWidth: 24, borderRadius: 4 },
  barLabel: { color: colors.muted, fontSize: 10 },
  material: { ...styles.card, flexDirection: 'row', alignItems: 'center' },
  details: { flex: 1 },
});
