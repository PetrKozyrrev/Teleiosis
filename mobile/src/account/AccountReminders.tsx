import { useEffect, useState } from 'react';
import { Action, Body, Card, Field } from '../components/ui';
import { Choice, Loading, Notice } from '../library/ui';
import { errorMessage, pageSize, maxOffset, type MaterialPage, type Request } from '../library/model';
import { Reminder } from './Reminder';

export function AccountReminders({ request }: { request: Request }) {
  const [expanded, setExpanded] = useState(false);
  return <>
    <Action title={expanded ? 'Скрыть напоминания по материалам' : 'Напоминания по материалам'} onPress={() => setExpanded(!expanded)} />
    {expanded && <ReminderMaterials request={request} />}
  </>;
}

function ReminderMaterials({ request }: { request: Request }) {
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const path = `/contents?limit=${pageSize}&offset=${offset}&sort=newest&q=${encodeURIComponent(query.trim())}` as const;
  const [result, setResult] = useState<{ path: string; revision: number; page?: MaterialPage; error?: string }>();
  const current = result?.path === path && result.revision === revision ? result : undefined;

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      void request(path, 'GET').then(value => {
        if (active) setResult({ path, revision, page: value as MaterialPage });
      }).catch(error => {
        if (active) setResult({ path, revision, error: errorMessage(error) });
      });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [path, request, revision]);

  return <>
    <Card>
      <Body>Выберите материал, чтобы назначить, перенести или отменить напоминание.</Body>
      <Field label="Найти материал для напоминания" value={query} maxLength={100} onChangeText={value => {
        setQuery(value); setOffset(0); setSelected(null);
      }} />
      {!current && <Loading />}
      {current?.error && <Notice>{current.error}</Notice>}
      {current?.page && (current.page.items.length ? <>
        <Choice label="Материал для напоминания" value={selected} onChange={setSelected} options={[
          { value: null, label: 'Выберите материал' },
          ...current.page.items.map(item => ({ value: item.id, label: item.title })),
        ]} />
        <Body>{offset + 1}–{offset + current.page.items.length} из {current.page.total}</Body>
        {offset > 0 && <Action title="Предыдущие материалы" onPress={() => { setOffset(offset - pageSize); setSelected(null); }} />}
        {offset + pageSize < current.page.total && offset + pageSize <= maxOffset &&
          <Action title="Следующие материалы" onPress={() => { setOffset(offset + pageSize); setSelected(null); }} />}
      </> : <Body>Материалы не найдены.</Body>)}
      <Action title="Обновить материалы для напоминаний" onPress={() => { setOffset(0); setRevision(value => value + 1); setSelected(null); }} />
    </Card>
    {selected !== null && <Reminder key={selected} id={selected} request={request} />}
  </>;
}
