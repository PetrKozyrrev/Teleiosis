import { randomUUID } from 'expo-crypto';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Text } from 'react-native';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Page, styles } from '../components/ui';
import { useTranslation } from '../i18n';
import type { Request } from '../library/model';
import { Loading, Notice } from '../library/ui';
import { reviewError, type Card as ReviewCard, type CardPage } from './model';

const pageSize = 50;
const changedQueue = 'Очередь изменилась. Загрузите её заново.';
type Rating = 'again' | 'remembered';
type Attempt = { rating: Rating; key: string };

async function duePage(request: Request, offset: number, limit: number) {
  return await request(`/mobile/review?due=true&offset=${offset}&limit=${limit}`, 'GET') as CardPage;
}

async function loadRound(request: Request, isCurrent: () => boolean) {
  const first = await duePage(request, 0, pageSize);
  const cards = new Map(first.items.map(card => [card.id, card]));
  for (let offset = pageSize; offset < first.total && isCurrent(); offset += pageSize) {
    const page = await duePage(request, offset, pageSize);
    if (page.total !== first.total || page.today !== first.today) throw new Error(changedQueue);
    for (const card of page.items) cards.set(card.id, card);
  }
  if (isCurrent() && cards.size !== first.total) throw new Error(changedQueue);
  return [...cards.values()];
}

export function ReviewSession({ request }: { request: Request }) {
  const t = useTranslation();
  const [round, setRound] = useState(0);
  const [queue, setQueue] = useState<ReviewCard[]>();
  const [loadError, setLoadError] = useState('');
  const [index, setIndex] = useState(0);
  const [answered, setAnswered] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [answerError, setAnswerError] = useState<{ text: string; stale: boolean }>();
  const [remaining, setRemaining] = useState<number>();
  const [countError, setCountError] = useState('');
  const [countRevision, setCountRevision] = useState(0);
  const attempt = useRef<Attempt | null>(null);
  const locking = useRef(false);
  const currentRequest = useRef(request);
  const lifetime = useRef(0);
  const card = queue?.[index];
  const finished = queue !== undefined && index === queue.length;

  useEffect(() => { currentRequest.current = request; }, [request]);
  useEffect(() => () => { lifetime.current++; }, []);

  useEffect(() => {
    void round;
    let active = true;
    void loadRound(currentRequest.current, () => active).then(cards => {
      if (active) setQueue(cards);
    }).catch(error => {
      if (active) setLoadError(error instanceof Error && error.message === changedQueue ? changedQueue : reviewError(error, true));
    });
    return () => { active = false; };
  }, [round]);

  useEffect(() => {
    void countRevision;
    if (!finished || queue?.length === 0) return;
    let active = true;
    void duePage(currentRequest.current, 0, 1).then(page => {
      if (active) setRemaining(page.total);
    }).catch(error => { if (active) setCountError(reviewError(error, true)); });
    return () => { active = false; };
  }, [finished, queue, countRevision]);

  function restart() {
    setQueue(undefined);
    setLoadError('');
    setRemaining(undefined);
    setCountError('');
    setIndex(0);
    setAnswered(0);
    setRound(value => value + 1);
  }

  function advance() {
    attempt.current = null;
    setRevealed(false);
    setAnswerError(undefined);
    setIndex(value => value + 1);
  }

  async function rate(rating: Rating) {
    if (!card || !revealed || locking.current || answerError?.stale) return;
    locking.current = true;
    setSaving(true);
    setAnswerError(undefined);
    const current = lifetime.current;
    const pending = attempt.current ?? { rating, key: randomUUID() };
    attempt.current = pending;
    try {
      await currentRequest.current(`/mobile/review/${card.id}/answers`, 'POST', { rating: pending.rating },
        { version: card.version, idempotencyKey: pending.key });
      if (current === lifetime.current) {
        setAnswered(value => value + 1);
        advance();
      }
    } catch (error) {
      if (current === lifetime.current) setAnswerError({
        text: reviewError(error),
        stale: error instanceof ApiError && !error.gateway && [404, 409, 410, 412].includes(error.status),
      });
    } finally {
      if (current === lifetime.current) { locking.current = false; setSaving(false); }
    }
  }

  return <Page title={t('Повторение')}>
    {loadError ? <Card>
      <Notice>{loadError}</Notice>
      <Action title={t('Загрузить заново')} onPress={restart} />
    </Card> : !queue && <Loading />}
    {card && queue && <Card featured>
      <Body>{t('Карточка {0} из {1}', index + 1, queue.length)}</Body>
      <Text style={styles.heading} accessibilityRole="header">{card.question}</Text>
      {revealed ? <>
        <Body>{card.answer}</Body>
        {card.takeaway ? <Body>{t('Мой вывод ·')} {card.takeaway}</Body> : null}
        {answerError ? <>
          <Notice>{answerError.text}</Notice>
          {answerError.stale ? <Action variant="outline" title={t('Пропустить карточку')} onPress={advance} />
            : <Action title={t('Повторить отправку оценки')} onPress={() => {
              if (attempt.current) void rate(attempt.current.rating);
            }} />}
        </> : <>
          <Action variant="outline" title={t('Помню')} disabled={saving} onPress={() => void rate('remembered')} />
          <Action variant="outline" title={t('Не помню')} disabled={saving} onPress={() => void rate('again')} />
          {saving && <Loading />}
        </>}
      </> : <Action title={t('Показать ответ')} onPress={() => setRevealed(true)} />}
    </Card>}
    {finished && <Card>
      <Text style={styles.heading} accessibilityRole="header">{t(queue.length ? 'Раунд завершён' : 'Карточек к повторению пока нет.')}</Text>
      <Body>{t('Обработано карточек: {0}', answered)}</Body>
      {(remaining !== undefined || queue.length === 0) && <Body>{t('Осталось к повторению: {0}', remaining ?? 0)}</Body>}
      {countError ? <>
        <Notice>{countError}</Notice>
        <Action variant="outline" title={t('Обновить счётчик')} onPress={() => {
          setCountError(''); setCountRevision(value => value + 1);
        }} />
      </> : remaining === undefined && queue.length > 0 && <Loading />}
      <Action title={t('На сегодня')} onPress={() => router.dismissTo('/')} />
      {remaining !== undefined && remaining > 0 && <Action variant="outline" title={t('Ещё один раунд')} onPress={restart} />}
    </Card>}
    <Action variant="text" title={t('Управление карточками')} disabled={saving} onPress={() => router.push('/review')} />
    {!finished && <Action variant="text" title={t('На сегодня')} disabled={saving} onPress={() => router.dismissTo('/')} />}
  </Page>;
}
