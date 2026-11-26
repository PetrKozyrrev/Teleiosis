import { randomUUID } from 'expo-crypto';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../auth/api';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { useTranslation } from '../i18n';
import { errorMessage, type Material, type Request } from '../library/model';
import { Choice, Loading, Notice } from '../library/ui';
import { forgetMaterial, remember } from '../offline/cache';
import { clearReflectionDraft, generation, reflectionDraft, saveReflectionDraft } from '../offline/store';

type Reflection = { thought: string; version: number };
type Context = {
  material: Material;
  tasks: { id: number; day: string; goal_name: string }[];
  reflection: Reflection | null;
};
type Result = { material: Material; task_completed: boolean };
type Attempt = { taskId: number | null; key: string; version: number };

function describe(error: unknown) {
  if (error instanceof ApiError && !error.gateway) {
    if (error.status === 0) return 'Для сохранения на сервере нужно подключение.';
    if (error.code === 'completion_task_missing') return 'Задание недоступно. Откройте материал из библиотеки или актуального плана.';
    if (error.code === 'reflection_version_changed') return 'Главная мысль изменилась. Обновите экран, чтобы сравнить версии.';
    if (error.status === 412) return 'Материал изменился. Обновите экран и повторите.';
    if (error.status === 404) return 'Материал или функция завершения недоступны.';
  }
  return errorMessage(error);
}

export function Completion({ id, taskId, reflectionOnly, request, owner }: {
  id: number; taskId: number | null; reflectionOnly: boolean; request: Request; owner: string | null;
}) {
  const t = useTranslation();
  const path = `/mobile/learning/materials/${id}` as const;
  const [context, setContext] = useState<Context>();
  const [result, setResult] = useState<Result>();
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [needsReload, setNeedsReload] = useState(false);
  const [selectedTask, setSelectedTask] = useState<number | null>(taskId);
  const [draft, setDraft] = useState<string | null>();
  const [storedDraft, setStoredDraft] = useState<string | null>(null);
  const [draftError, setDraftError] = useState(false);
  const [busy, setBusy] = useState(false);
  const attempt = useRef<Attempt | null>(null);
  const locked = useRef(false);
  const draftWrite = useRef(0);

  useFocusEffect(useCallback(() => {
    void revision;
    let active = true;
    setLoading(true);
    setMessage('');
    void request(`${path}/completion`, 'GET').then(value => {
      if (!active) return;
      const latest = value as Context;
      setContext(latest);
      if (latest.material.status !== 'studied') {
        setResult(undefined);
      }
      setNeedsReload(false);
    }).catch(error => {
      if (active) { setContext(undefined); setMessage(describe(error)); }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, request, revision]));

  useEffect(() => {
    let active = true;
    const load = owner ? reflectionDraft(owner, id) : Promise.resolve(null);
    void load.then(value => { if (active) { setDraft(value); setStoredDraft(value); } }).catch(() => {
      if (active) { setDraft(null); setDraftError(true); }
    });
    return () => { active = false; };
  }, [id, owner]);

  async function run(operation: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try {
      await operation();
    } catch (error) {
      setMessage(describe(error));
      if (error instanceof ApiError && error.status === 412) {
        attempt.current = null;
        setNeedsReload(true);
      }
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  function confirm() {
    const version = context?.material.version;
    if (!version || needsReload) return;
    const selected = taskId ?? selectedTask;
    const operation = attempt.current?.taskId === selected
      ? attempt.current : { taskId: selected, key: randomUUID(), version };
    attempt.current = operation;
    void run(async () => {
      const expected = owner ? generation(owner) : undefined;
      const saved = await request(`${path}/completion`, 'POST', { task_id: operation.taskId },
        { version: operation.version, idempotencyKey: operation.key }) as Result;
      if (saved.material.status === 'studied' && (!operation.taskId || saved.task_completed)) setResult(saved);
      setContext(current => current && { ...current, material: saved.material });
      if (owner) {
        await forgetMaterial(owner, id).catch(() => {});
        await remember(owner, `/contents/${id}`, saved.material, expected).catch(() => {});
      }
      if (saved.material.status !== 'studied' || (operation.taskId && !saved.task_completed)) {
        attempt.current = null;
        setMessage('Состояние изменилось после сохранения. Проверьте материал и план.');
        setNeedsReload(true);
      }
    });
  }

  function changeDraft(text: string) {
    setDraft(text);
    if (!owner) return;
    const write = ++draftWrite.current;
    void saveReflectionDraft(owner, id, text, generation(owner)).then(() => {
      if (draftWrite.current === write) {
        setStoredDraft(text.trim() ? text : null);
        setDraftError(false);
      }
    }).catch(() => { if (draftWrite.current === write) setDraftError(true); });
  }

  function saveThought() {
    if (!context || !draft?.trim() || needsReload) return;
    const text = draft;
    const local = owner ? { owner, version: generation(owner) } : null;
    void run(async () => {
      const saved = await request(`${path}/reflection`, 'PUT', { thought: text.trim(), previous: context.reflection?.version ?? null }) as Reflection;
      setContext(current => current && { ...current, reflection: saved });
      if (local) await clearReflectionDraft(local.owner, id, text, local.version).catch(() => {});
      setDraft(null);
      setStoredDraft(null);
      setDraftError(false);
      setMessage('Главная мысль сохранена.');
    });
  }

  function done() {
    if (router.canGoBack()) router.back();
    else router.dismissTo('/library');
  }

  const completed = result?.material.status === 'studied';
  const showReflection = Boolean(completed || reflectionOnly || draft?.trim());
  const canConfirm = Boolean(context && (!selectedTask || taskId || context.tasks.some(task => task.id === selectedTask)));
  const thought = draft ?? context?.reflection?.thought ?? '';
  return <Page title={t('Завершение изучения')} subtitle={context?.material.title}>
    {message && <Notice>{message}</Notice>}
    {loading && !context && <Loading />}
    {!reflectionOnly && !completed && <Card>
      {taskId ? <Body>{t('Будет завершено задание, из которого открыт материал.')}</Body> : context && context.tasks.length > 0 &&
        <Choice label={t('Также завершить задание')} value={selectedTask} disabled={busy || loading}
          onChange={setSelectedTask} options={[{ value: null, label: t('Только материал') },
            ...context.tasks.map(task => ({ value: task.id, label: `${task.goal_name} · ${task.day}` }))]} />}
      <Action title={t('Отметить изученным')} disabled={busy || loading || needsReload || !canConfirm} onPress={confirm} />
    </Card>}
    {completed && <Card>
      <Notice>{t(result.task_completed ? 'Материал изучен. Задание завершено.' : 'Материал изучен')}</Notice>
    </Card>}
    {showReflection && <Card>
      <Field label={t('Главная мысль (необязательно)')} maxLength={4000} multiline value={thought}
        editable={!busy && draft !== undefined} onChangeText={changeDraft} />
      {(draftError || (!owner && draft?.trim())) && <Notice>{t('Не удалось сохранить черновик на устройстве.')}</Notice>}
      {!context && draft?.trim() && !draftError && draft === storedDraft && <Body>{t('Черновик сохранён на устройстве.')}</Body>}
      {draft?.trim() && context?.reflection && thought.trim() !== context.reflection.thought &&
        <Body>{t('Сохранённая на сервере мысль: {0}', context.reflection.thought)}</Body>}
      <Action variant="outline" title={t('Сохранить главную мысль')}
        disabled={busy || loading || needsReload || !context || !draft?.trim()}
        onPress={saveThought} />
    </Card>}
    {(!context || needsReload) && !loading && <Action variant="outline" title={t('Обновить')} disabled={busy}
      onPress={() => setRevision(value => value + 1)} />}
    {completed && <>
      <Action variant="outline" title={t('Создать вопрос для повторения')} disabled={busy}
        onPress={() => router.push({ pathname: '/review', params: { id: String(id) } })} />
      <Action variant="outline" title={t('Выбрать следующий материал')} disabled={busy}
        onPress={() => router.dismissTo('/library')} />
    </>}
    <Action variant="text" title={t(completed || reflectionOnly ? 'Готово' : 'Отмена')} disabled={busy} onPress={done} />
  </Page>;
}
