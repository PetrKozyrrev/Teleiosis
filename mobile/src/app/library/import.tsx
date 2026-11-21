import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../../auth/api';
import { useAuth } from '../../auth/context';
import { Action, Body, Card, Page } from '../../components/ui';
import { importError, pickImportFile, submitImport, type ImportFile, type ImportSummary } from '../../library/import';
import type { Request } from '../../library/model';
import { LibraryAccess, Loading, Notice } from '../../library/ui';

export default function ImportLibrary() {
  return <LibraryAccess>{request => <ImportView request={request} />}</LibraryAccess>;
}

function ImportView({ request }: { request: Request }) {
  const { controller, state } = useAuth();
  const [file, setFile] = useState<ImportFile | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [applied, setApplied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const running = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function run(action: (current: () => boolean) => Promise<void>, applying = false) {
    if (running.current) return;
    const sameSession = controller.captureSession();
    const current = () => mounted.current && sameSession();
    running.current = true;
    setBusy(true);
    setMessage('');
    try {
      await action(current);
    } catch (error) {
      if (!current()) return;
      if (applying && error instanceof ApiError && error.status === 409) setSummary(null);
      setMessage(importError(error, applying));
    } finally {
      running.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  function choose() {
    void run(async current => {
      const selected = await pickImportFile();
      if (!selected || !current()) return;
      setFile(selected);
      setSummary(null);
      setApplied(false);
    });
  }

  function send(mode: 'preview' | 'apply') {
    if (!file) return;
    void run(async current => {
      if (mode === 'preview') setSummary(null);
      const result = await submitImport(request, mode, file);
      if (!current()) return;
      setSummary(result);
      if (mode === 'apply' || result.replayed) {
        setApplied(true);
        setFile(null);
      }
    }, mode === 'apply');
  }

  return <Page title="Импорт библиотеки"><Card>
    <Body>Выберите JSON-выгрузку Teleiosis до 2 МиБ и 500 материалов. Для проверки и импорта требуется подключение.</Body>
    {state.session?.user.email && <Body>Аккаунт: {state.session.user.email}</Body>}
    <Action title="Выбрать файл" disabled={busy} onPress={choose} />
    {file && <>
      <Body>{file.name}</Body>
      <Action title={summary ? 'Проверить ещё раз' : 'Проверить файл'} disabled={busy} onPress={() => send('preview')} />
    </>}
    {summary && <>
      <Notice>{summary.replayed ? 'Этот файл уже был импортирован. Результат первого импорта.' :
        applied ? 'Импорт завершён.' : 'Предварительный результат'}</Notice>
      <Body>Материалы: {summary.materials} · Повторы: {summary.duplicates}</Body>
      <Body>Категории: {summary.categories} · Теги: {summary.tags} · Коллекции: {summary.collections} · Назначения: {summary.memberships}</Body>
      {!applied && <>
        <Body>У повторов сохранятся существующие данные и назначения.</Body>
        <Action title="Импортировать" disabled={busy} onPress={() => send('apply')} />
      </>}
    </>}
    {busy && <Loading />}
    {message && <Notice>{message}</Notice>}
  </Card></Page>;
}
