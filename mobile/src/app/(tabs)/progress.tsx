import { useCallback, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { Action, Body, Card, Page } from '../../components/ui';
import { LibraryAccess, Loading, Notice } from '../../library/ui';
import { errorMessage, statuses, type Request } from '../../library/model';

type Stats = {
  total: number; by_status: Record<keyof typeof statuses, number>; studied_share: number | null;
  return_share: number | null; added_7d: number; studied_7d: number;
  top_categories: { id: number; name: string; count: number }[];
  days: { day: string; added: number; studied: number }[];
};
const percent = (value: number | null) => value === null ? 'Пока нет данных' : `${Math.round(value * 100)} %`;

export default function Progress() {
  return <LibraryAccess>{request => <ProgressView request={request} />}</LibraryAccess>;
}
function ProgressView({ request }: { request: Request }) {
  const [result, setResult] = useState<{ value: Stats; revision: number }>();
  const stats = result?.value;
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  useFocusEffect(useCallback(() => {
    let active = true;
    setResult(undefined); setMessage('');
    void request('/stats', 'GET').then(value => { if (active) setResult({ value: value as Stats, revision }); })
      .catch(error => { if (active) setMessage(errorMessage(error)); });
    return () => { active = false; };
  }, [request, revision]));
  return <Page title="Прогресс">
    {stats ? <>
      <Card><Body>Материалов · {stats.total}</Body>
        {Object.entries(statuses).map(([key, label]) => <Body key={key}>{label} · {stats.by_status[key as keyof typeof statuses]}</Body>)}
        <Body>Доля изученного · {percent(stats.studied_share)}</Body>
        <Body>Возврат к оригиналу · {percent(stats.return_share)}</Body>
      </Card>
      <Card><Body>За семь дней добавлено · {stats.added_7d}</Body><Body>Изучено · {stats.studied_7d}</Body>
        {stats.days.map(day => <Body key={day.day}>{day.day} · добавлено {day.added}, изучено {day.studied}</Body>)}
      </Card>
      {stats.top_categories.length > 0 && <Card>{stats.top_categories.map(category => <Body key={category.id}>{category.name} · {category.count}</Body>)}</Card>}
    </> : message ? <Notice>{message}</Notice> : <Loading />}
    <Action title="Обновить прогресс" onPress={() => setRevision(value => value + 1)} />
  </Page>;
}
