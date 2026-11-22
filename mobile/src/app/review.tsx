import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { randomUUID } from 'expo-crypto';
import { useCallback, useRef, useState } from 'react';
import { Alert } from 'react-native';
import { Action, Body, Card as Panel, Field, Page } from '../components/ui';
import { Choice, LibraryAccess, Loading, Notice } from '../library/ui';
import { parseId, type Request } from '../library/model';
import { validDay } from '../plan/model';
import { reviewError, type Card, type CardPage, type HistoryPage } from '../review/model';

type Save = (operation: () => Promise<unknown>, after?: () => void) => Promise<void>;

export default function ReviewRoute() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  return <LibraryAccess>{request => <Review request={request} contentId={parseId(id)} />}</LibraryAccess>;
}

function Review({ request, contentId }: { request: Request; contentId: number | null }) {
  const [due, setDue] = useState(contentId === null);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<CardPage>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [takeaway, setTakeaway] = useState('');
  const [createKey, setCreateKey] = useState<string | null>(null);
  const locked = useRef(false);
  const generation = useRef(0);
  useFocusEffect(useCallback(() => {
    void revision;
    const current = ++generation.current;
    setResult(undefined); setBusy(false); setStale(false); locked.current = false;
    const params = new URLSearchParams({ due: String(due), offset: String(offset), limit: '20' });
    if (contentId) params.set('content_id', String(contentId));
    void request(`/mobile/review?${params}`, 'GET').then(value => {
      if (generation.current === current) setResult(value as CardPage);
    }).catch(error => { if (generation.current === current) setMessage(reviewError(error, true)); });
    return () => { generation.current++; };
  }, [request, contentId, due, offset, revision]));

  const refresh = () => { setMessage(''); setRevision(value => value + 1); };
  const save: Save = async (operation, after) => {
    if (locked.current || stale || !result) return;
    const current = generation.current;
    locked.current = true; setBusy(true); setMessage('');
    try {
      await operation();
      if (current !== generation.current) return;
      after?.();
      setResult(undefined); setRevision(value => value + 1);
    } catch (error) {
      if (current === generation.current) { setMessage(reviewError(error)); setStale(true); }
    } finally {
      if (current === generation.current) { locked.current = false; setBusy(false); }
    }
  };
  function changeText(set: (value: string) => void, value: string) {
    set(value); setCreateKey(null);
  }
  const disabled = busy || stale || !result;
  return <Page title="Карточки для повторения">
    <Choice label="Показать" value={due ? 'due' : 'all'} disabled={busy}
      options={[{ value: 'due', label: 'Пора повторить' }, { value: 'all', label: 'Все карточки' }]}
      onChange={value => { setDue(value === 'due'); setOffset(0); setMessage(''); }} />
    {message ? <Notice>{message}</Notice> : null}
    {result ? <>
      <Body>Карточек · {result.total}</Body>
      {contentId ? <Panel>
        <Field label="Вопрос" value={question} maxLength={500} multiline editable={!busy} onChangeText={v => changeText(setQuestion, v)} />
        <Field label="Ответ" value={answer} maxLength={4000} multiline editable={!busy} onChangeText={v => changeText(setAnswer, v)} />
        <Field label="Мой вывод (необязательно)" value={takeaway} maxLength={4000} multiline editable={!busy} onChangeText={v => changeText(setTakeaway, v)} />
        <Action title="Создать карточку" disabled={disabled || !question.trim() || !answer.trim()}
          onPress={() => {
            const key = createKey ?? randomUUID();
            setCreateKey(key);
            void save(() => request('/mobile/review', 'POST', { content_id: contentId, question: question.trim(),
              answer: answer.trim(), takeaway: takeaway.trim() }, { idempotencyKey: key }),
            () => { setQuestion(''); setAnswer(''); setTakeaway(''); setCreateKey(null); });
          }} />
      </Panel> : <Action title="Добавить карточки из материала" disabled={busy} onPress={() => router.dismissTo('/')} />}
      {result.items.length === 0 && <Body>{due ? 'Карточек к повторению пока нет.' : 'Карточек пока нет.'}</Body>}
      {result.items.map(card => <ReviewItem key={card.id + '-' + card.version} card={card} request={request} save={save} disabled={disabled} />)}
      {offset > 0 && <Action title="Предыдущие карточки" disabled={busy} onPress={() => { setMessage(''); setOffset(offset - 20); }} />}
      {offset + 20 < result.total && <Action title="Следующие карточки" disabled={busy} onPress={() => { setMessage(''); setOffset(offset + 20); }} />}
    </> : !message && <Loading />}
    <Action title="Обновить карточки" disabled={busy} onPress={refresh} />
  </Page>;
}

function ReviewItem({ card, request, save, disabled }: { card: Card; request: Request; save: Save; disabled: boolean }) {
  const [shown, setShown] = useState(false);
  const [editing, setEditing] = useState(false);
  const [question, setQuestion] = useState(card.question);
  const [answer, setAnswer] = useState(card.answer);
  const [takeaway, setTakeaway] = useState(card.takeaway);
  const [day, setDay] = useState(card.due_on);
  const [paused, setPaused] = useState(card.paused);
  const [history, setHistory] = useState<HistoryPage>();
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyError, setHistoryError] = useState('');
  const [historyBusy, setHistoryBusy] = useState(false);
  const historyEpoch = useRef(0);
  useFocusEffect(useCallback(() => () => { historyEpoch.current++; }, []));
  const path = `/mobile/review/${card.id}` as const;
  const options = { version: card.version };

  function rate(rating: 'again' | 'remembered') {
    const key = randomUUID();
    void save(() => request(`${path}/answers`, 'POST', { rating }, { ...options, idempotencyKey: key }));
  }
  async function loadHistory(offset: number) {
    const current = ++historyEpoch.current;
    setHistoryBusy(true); setHistoryError('');
    try {
      const value = await request(`${path}/history?offset=${offset}&limit=20`, 'GET');
      if (current === historyEpoch.current) { setHistory(value as HistoryPage); setHistoryOffset(offset); }
    } catch (error) {
      if (current === historyEpoch.current) setHistoryError(reviewError(error));
    } finally {
      if (current === historyEpoch.current) setHistoryBusy(false);
    }
  }
  return <Panel>
    <Body>{card.title}</Body><Body>{card.question}</Body>
    <Body>Повторение · {card.due_on}{card.paused ? ' · приостановлено' : ''}</Body>
    <Action title="Открыть материал" onPress={() => router.push({ pathname: '/library/[id]', params: { id: String(card.content_id) } })} />
    {!editing && <>
      {shown ? <><Body>{card.answer}</Body>{card.takeaway ? <Body>Мой вывод · {card.takeaway}</Body> : null}
        {!card.paused && <>
          <Action title="Не помню" disabled={disabled} onPress={() => rate('again')} />
          <Action title="Помню" disabled={disabled} onPress={() => rate('remembered')} />
        </>}
      </> : <Action title="Показать ответ" disabled={disabled} onPress={() => setShown(true)} />}
      <Action title="Изменить карточку и расписание" disabled={disabled} onPress={() => setEditing(true)} />
    </>}
    {editing && <>
      <Field label="Изменить вопрос" multiline value={question} onChangeText={setQuestion} maxLength={500} editable={!disabled} />
      <Field label="Изменить ответ" multiline value={answer} onChangeText={setAnswer} maxLength={4000} editable={!disabled} />
      <Field label="Изменить вывод" multiline value={takeaway} onChangeText={setTakeaway} maxLength={4000} editable={!disabled} />
      <Field label="Дата повторения (ГГГГ-ММ-ДД)" value={day} onChangeText={setDay} maxLength={10} editable={!disabled} />
      <Choice label="Повторение" value={paused ? 'paused' : 'active'} disabled={disabled} onChange={v => setPaused(v === 'paused')}
        options={[{ value: 'active', label: 'Активно' }, { value: 'paused', label: 'Приостановлено' }]} />
      <Action title="Сохранить карточку" disabled={disabled || !question.trim() || !answer.trim() || !validDay(day)}
        onPress={() => void save(() => request(path, 'PUT', { question: question.trim(), answer: answer.trim(),
          takeaway: takeaway.trim(), due_on: day, paused }, options))} />
      <Action title="Отменить изменения" disabled={disabled} onPress={() => setEditing(false)} />
      <Action title="Удалить карточку" disabled={disabled} onPress={() => Alert.alert('Удалить карточку?', 'Карточка и история её ответов будут удалены.',
        [{ text: 'Отмена', style: 'cancel' }, { text: 'Удалить', style: 'destructive', onPress: () => void save(() => request(path, 'DELETE', undefined, options)) }])} />
    </>}
    <Action title="История ответов" disabled={disabled || historyBusy} onPress={() => void loadHistory(0)} />
    {historyError && <Notice>{historyError}</Notice>}
    {history && <>
      {history.total === 0 && <Body>Ответов пока нет.</Body>}
      {history.items.map(row => <Body key={row.id}>{row.occurred_at.slice(0, 10)} · {row.rating === 'again' ? 'Не помню' : 'Помню'} · следующее {row.due_on}</Body>)}
      {historyOffset > 0 && <Action title="Более новые ответы" disabled={disabled || historyBusy} onPress={() => void loadHistory(historyOffset - 20)} />}
      {historyOffset + 20 < history.total && <Action title="Более ранние ответы" disabled={disabled || historyBusy} onPress={() => void loadHistory(historyOffset + 20)} />}
    </>}
  </Panel>;
}
