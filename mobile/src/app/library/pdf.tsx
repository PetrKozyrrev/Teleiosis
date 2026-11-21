import { useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import type { File } from 'expo-file-system';
import { useAuth } from '../../auth/context';
import { Action, Body, Card, Page } from '../../components/ui';
import { parseId, type Request } from '../../library/model';
import { LibraryAccess, Loading, Notice } from '../../library/ui';
import { pdfError, pdfPath, readPdf, removePreview, writePdfPreview, type PdfMetadata } from '../../library/pdf';

export default function PdfRoute() {
  const params = useLocalSearchParams<{ id?: string }>();
  const id = parseId(params.id);
  if (id === null) return <Page title="PDF"><Notice>Материал недоступен.</Notice></Page>;
  return <LibraryAccess>{request => <PdfView key={id} id={id} request={request} />}</LibraryAccess>;
}

function PdfView({ id, request }: { id: number; request: Request }) {
  const { controller } = useAuth();
  const [metadata, setMetadata] = useState<PdfMetadata>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const mounted = useRef(false);
  const running = useRef(false);
  const preview = useRef<File | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      removePreview(preview.current);
    };
  }, []);

  useEffect(() => {
    let active = true;
    void readPdf(request, id).then(value => {
      if (active) setMetadata(value);
    }).catch(error => { if (active) setMessage(pdfError(error)); });
    return () => { active = false; };
  }, [request, id, revision]);

  async function open() {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setMessage('');
    const sameSession = controller.captureSession();
    try {
      const data = await request(`${pdfPath(id)}/download`, 'GET') as ArrayBuffer;
      if (!mounted.current || !sameSession()) return;
      const file = writePdfPreview(data);
      removePreview(preview.current);
      preview.current = file;
      await file.preview();
    } catch (error) {
      if (mounted.current && sameSession()) setMessage(pdfError(error));
    } finally {
      running.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return <Page title="PDF"><Card>
    {(!metadata && !message || busy) && <Loading />}
    {metadata && <>
      <Body>{metadata.name} · {metadata.size_bytes.toLocaleString('ru-RU')} Б</Body>
      <Action title="Открыть PDF" disabled={busy} onPress={() => void open()} />
    </>}
    {message && <>
      <Notice>{message}</Notice>
      {!metadata && <Action title="Повторить загрузку" onPress={() => {
        setMessage('');
        setRevision(value => value + 1);
      }} />}
    </>}
  </Card></Page>;
}
