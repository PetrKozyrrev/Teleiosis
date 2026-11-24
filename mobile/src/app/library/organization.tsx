import { useCallback, useRef, useState, type ComponentRef } from 'react';
import { Alert, Text, type ScrollView } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import { uncertainCreate, type Request } from '../../library/model';
import { groupLabels, groupPath, organizationError, type Group, type GroupKind } from '../../library/organization';
import { Choice, LibraryAccess, Loading, Notice } from '../../library/ui';

export default function OrganizationRoute() {
  const [kind, setKind] = useState<GroupKind>('tags');
  return <LibraryAccess>{request => <GroupManager key={kind} kind={kind} setKind={setKind} request={request} />}</LibraryAccess>;
}

function GroupManager({ kind, setKind, request }: { kind: GroupKind; setKind: (kind: GroupKind) => void; request: Request }) {
  const [items, setItems] = useState<Group[] | null>(null);
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<Group | null>(null);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);
  const path = groupPath(kind);
  useFocusEffect(useCallback(() => {
    void revision; // Explicit refresh also reloads the currently focused screen.
    let active = true;
    void request(path, 'GET').then(value => {
      if (active) { setItems(value as Group[]); setLoadError(''); }
    }).catch(error => { if (active) setLoadError(organizationError(error, true)); });
    return () => { active = false; };
  }, [path, request, revision]));

  async function change(group: Group | null, method: 'POST' | 'PATCH' | 'DELETE') {
    if (locked.current) return;
    locked.current = true; setBusy(true); setMessage('');
    try {
      await request(group ? `/mobile/library/${kind}/${group.id}` : path, method,
        method === 'DELETE' ? undefined : { name: name.trim() });
      setEditing(null); setName(''); setRevision(value => value + 1);
      setMessage(method === 'DELETE' ? 'Удалено. Материалы сохранены.' : 'Сохранено.');
    } catch (error) {
      setMessage(method === 'POST' && uncertainCreate(error)
        ? 'Ответ не получен. Обновите список перед повтором: запись могла сохраниться.' : organizationError(error));
    } finally { locked.current = false; setBusy(false); }
  }
  return <Page title="Теги и коллекции" scrollRef={scrollRef}>
    <Choice label="Раздел" value={kind} onChange={setKind} disabled={busy}
      options={[{ value: 'tags', label: groupLabels.tags }, { value: 'collections', label: groupLabels.collections }]} />
    <Body>Категория — основной раздел материала. Теги отмечают темы, а коллекции собирают материалы из разных разделов в подборки.</Body>
    <Body>{kind === 'tags' ? 'Например, «UX» и «Исследования».' : 'Например, «На выходные».'} Изменения доступны при подключении к серверу.</Body>
    <Card>
      <Text accessibilityRole="header" style={styles.heading}>{editing ? 'Переименование' : kind === 'tags' ? 'Новый тег' : 'Новая коллекция'}</Text>
      <Field label={kind === 'tags' ? 'Название тега' : 'Название коллекции'} value={name} onChangeText={setName}
        maxLength={50} editable={!busy} autoCapitalize="sentences" />
      <Action title={busy ? 'Сохранение…' : editing ? 'Сохранить название' : kind === 'tags' ? 'Создать тег' : 'Создать коллекцию'}
        disabled={busy || !name.trim()} onPress={() => void change(editing, editing ? 'PATCH' : 'POST')} />
      {editing && <Action title="Отменить переименование" disabled={busy} onPress={() => { setEditing(null); setName(''); }} />}
      {message && <Notice>{message}</Notice>}
    </Card>
    <Action title="Обновить теги и коллекции" disabled={busy} onPress={() => setRevision(value => value + 1)} />
    {loadError && <Notice>{loadError}</Notice>}
    {!items && !loadError && <Loading />}
    {items?.length === 0 && <Body>{kind === 'tags' ? 'Тегов пока нет.' : 'Коллекций пока нет.'}</Body>}
    {items?.map(group => <Card key={group.id}>
      <Text style={styles.heading}>{group.name}</Text><Body>Материалов · {group.contents_count}</Body>
      <Action title={`Переименовать «${group.name}»`} disabled={busy} onPress={() => { setEditing(group); setName(group.name); setMessage(''); scrollRef.current?.scrollTo({ y: 0, animated: true }); }} />
      <Action title={`Удалить «${group.name}»`} disabled={busy} onPress={() => Alert.alert('Удалить?', 'Материалы останутся в библиотеке.', [
        { text: 'Отмена', style: 'cancel' }, { text: 'Удалить', style: 'destructive', onPress: () => void change(group, 'DELETE') },
      ])} />
    </Card>)}
  </Page>;
}
