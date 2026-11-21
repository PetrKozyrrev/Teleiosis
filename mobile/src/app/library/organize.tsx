import { useCallback, useRef, useState } from 'react';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { ApiError } from '../../auth/api';
import { Action, Body, Card, Page } from '../../components/ui';
import { parseId, type Request } from '../../library/model';
import { groupPath, organizationError, organizationPath, type Group, type Organization } from '../../library/organization';
import { GroupSelection } from '../../library/GroupSelection';
import { LibraryAccess, Loading, Notice } from '../../library/ui';

export default function OrganizeRoute() {
  const params = useLocalSearchParams<{ id: string }>();
  const id = parseId(params.id);
  return <LibraryAccess>{request => id ? <Organize key={id} id={id} request={request} />
    : <Page title="Теги и коллекции материала"><Notice>Материал не найден.</Notice></Page>}</LibraryAccess>;
}

function Organize({ id, request }: { id: number; request: Request }) {
  const [result, setResult] = useState<{ organization: Organization; tags: Group[]; collections: Group[] } | null>(null);
  const [tags, setTags] = useState<number[]>([]);
  const [collections, setCollections] = useState<number[]>([]);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState('');
  const [loadError, setLoadError] = useState('');
  const [mustReload, setMustReload] = useState(false);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  useFocusEffect(useCallback(() => {
    void revision; // Explicit refresh also reloads the currently focused screen.
    let active = true;
    setResult(null); setLoadError('');
    void Promise.all([request(organizationPath(id), 'GET'), request(groupPath('tags'), 'GET'), request(groupPath('collections'), 'GET')])
      .then(([value, tagList, collectionList]) => {
        if (!active) return;
        const organization = value as Organization;
        setResult({ organization, tags: tagList as Group[], collections: collectionList as Group[] });
        setTags(organization.tags.map(tag => tag.id)); setCollections(organization.collections.map(collection => collection.id));
        setMustReload(false);
      }).catch(error => { if (active) setLoadError(organizationError(error, true)); });
    return () => { active = false; };
  }, [id, request, revision]));

  const dirty = result && (tags.length !== result.organization.tags.length || collections.length !== result.organization.collections.length
    || tags.some(id => !result.organization.tags.some(tag => tag.id === id))
    || collections.some(id => !result.organization.collections.some(collection => collection.id === id)));
  async function save() {
    if (locked.current || !result || mustReload) return;
    locked.current = true; setBusy(true); setMessage('');
    try {
      const organization = await request(organizationPath(id), 'PATCH', { tag_ids: tags, collection_ids: collections },
        { version: result.organization.version }) as Organization;
      setResult({ ...result, organization });
      setMessage('Теги и коллекции сохранены.');
    } catch (error) {
      const uncertain = error instanceof ApiError && (error.status === 0 || error.status >= 500);
      setMustReload(true);
      setMessage(uncertain ? 'Ответ не получен. Изменения могли сохраниться. Обновите данные перед повтором.' : organizationError(error));
    } finally { locked.current = false; setBusy(false); }
  }
  return <Page title="Теги и коллекции материала">
    <Body>У материала может быть до 20 тегов и 20 коллекций. Изменения требуют подключения к серверу.</Body>
    {loadError && <Notice>{loadError}</Notice>}
    {!result && !loadError && <Loading />}
    {result && <Card>
      <GroupSelection label="Теги" items={result.tags} selected={tags} onChange={setTags} disabled={busy} />
      <GroupSelection label="Коллекции" items={result.collections} selected={collections} onChange={setCollections} disabled={busy} />
      <Action title={busy ? 'Сохранение…' : 'Сохранить теги и коллекции'} disabled={busy || !dirty || mustReload} onPress={() => void save()} />
    </Card>}
    {message && <Notice>{message}</Notice>}
    <Action title="Загрузить актуальные теги и коллекции" disabled={busy} onPress={() => { setMessage(''); setRevision(value => value + 1); }} />
    <Action title="Управлять тегами и коллекциями" disabled={busy || Boolean(dirty)} onPress={() => router.push('/library/organization')} />
    {dirty && <Body>Сохраните выбор перед переходом к управлению тегами и коллекциями.</Body>}
  </Page>;
}
