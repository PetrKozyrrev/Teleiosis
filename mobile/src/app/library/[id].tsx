import { router, useFocusEffect, useLocalSearchParams, useNavigation } from 'expo-router';
import { openURL } from 'expo-linking';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Text } from 'react-native';
import { ApiError } from '../../auth/api';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import {
  errorMessage, linkInput, originalUrl, parseId, sources, statuses,
  type Category, type Material, type Request, type Status,
} from '../../library/model';
import { Choice, LibraryAccess, Loading, Notice, optionsOf } from '../../library/ui';
import { createPdf, pdfCreatePath, pdfError, pickPdf, type SelectedPdf } from '../../library/pdf';
import { cachedCategories, cachedMaterial, forgetMaterial, readOnline, remember } from '../../offline/cache';
import { enqueue, generation, getJob, unassigned, type Draft } from '../../offline/store';
import { GroupSelection } from '../../library/GroupSelection';
import { groupPath, organizationPath, type Group, type Organization } from '../../library/organization';

export default function MaterialRoute() {
  const { id: param, draftId, inbox, edit } = useLocalSearchParams<{ id: string; draftId?: string; inbox?: string; edit?: string }>();
  const id = param === 'new' ? 'new' : parseId(param);
  if (id === 'new' && draftId && inbox === '1') {
    return <MaterialScreen key={draftId} request={async () => { throw new ApiError(401); }} id={id} owner={unassigned} draftId={draftId} />;
  }
  return <LibraryAccess>{(request, owner) => id
    ? <MaterialScreen key={draftId ?? id} request={request} id={id} owner={owner} draftId={id === 'new' ? draftId : undefined}
      openEditor={edit === '1'} />
    : <Page title="Материал"><Notice>Материал не найден.</Notice></Page>}
  </LibraryAccess>;
}

function MaterialScreen({ id, request, owner, draftId, openEditor }: {
  id: number | 'new'; request: Request; owner: string | null; draftId?: string; openEditor?: boolean;
}) {
  const navigation = useNavigation();
  const [item, setItem] = useState<Material | null>(null);
  const [cachedAt, setCachedAt] = useState<number>();
  const [draftReady, setDraftReady] = useState(!draftId);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryError, setCategoryError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [revision, setRevision] = useState(0);
  const [categoryRevision, setCategoryRevision] = useState(0);
  const [editing, setEditing] = useState(id === 'new');
  const [url, setUrl] = useState('');
  const [kind, setKind] = useState<'link' | 'note' | 'pdf'>('link');
  const [selectedPdf, setSelectedPdf] = useState<SelectedPdf | null>(null);
  const [title, setTitle] = useState('');
  const [note, setNote] = useState('');
  const [status, setStatus] = useState<Status>('unseen');
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [groups, setGroups] = useState<Group[]>();
  const [selected, setSelected] = useState<number[]>([]);
  const [initialCollections, setInitialCollections] = useState<number[]>([]);
  const [collectionError, setCollectionError] = useState('');
  const hydratedCollections = useRef(false);
  const [editBase, setEditBase] = useState<Material>();
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [message, setMessage] = useState('');
  const [staleEdit, setStaleEdit] = useState(false);
  const original = originalUrl(item?.url ?? null);
  const creatingPdf = id === 'new' && kind === 'pdf';
  const launchEditor = useRef(openEditor);

  const beginEdit = useCallback((material: Material) => {
    setEditBase(material);
    setTitle(material.title);
    setUrl(material.url ?? '');
    setNote(material.note ?? '');
    setStatus(material.status);
    setCategoryId(material.category_id);
    setGroups(undefined);
    setSelected([]);
    setInitialCollections([]);
    setCollectionError('');
    hydratedCollections.current = false;
    setMessage('');
    setEditing(true);
  }, []);

  useFocusEffect(useCallback(() => {
    void revision; // Refresh the card explicitly or when returning from organization.
    let active = true;
    if (id !== 'new') {
      void readOnline(owner, request, `/contents/${id}`, key => cachedMaterial(key, id)).then(result => {
        if (!active) return;
        setItem(result.value);
        setCachedAt(result.cachedAt);
        if (launchEditor.current && result.cachedAt === undefined) {
          launchEditor.current = false;
          beginEdit(result.value);
        }
      }).catch(error => {
        if (!active) return;
        if (owner && error instanceof ApiError && error.status === 404) void forgetMaterial(owner, id).catch(() => {});
        setLoadError(errorMessage(error));
      });
    }
    return () => { active = false; };
  }, [beginEdit, id, owner, request, revision]));

  useEffect(() => {
    if (!editing || owner === unassigned || creatingPdf) return;
    let active = true;
    void Promise.all([
      request(groupPath('collections'), 'GET'),
      id === 'new' ? Promise.resolve(null) : request(organizationPath(id), 'GET'),
    ]).then(([values, linked]) => {
      if (!active || !Array.isArray(values)) return;
      const organization = linked as Organization | null;
      if (id !== 'new' && (!organization || organization.version !== editBase?.version)) {
        setCollectionError('Коллекции изменились. Загрузите актуальную карточку перед их редактированием.');
        return;
      }
      if (organization && !hydratedCollections.current) {
        hydratedCollections.current = true;
        const ids = organization.collections.map(collection => collection.id);
        setSelected(ids);
        setInitialCollections(ids);
      }
      setGroups(values as Group[]);
      setCollectionError('');
    }).catch(() => { if (active) setCollectionError('Коллекции недоступны. Для их изменения подключитесь к серверу.'); });
    return () => { active = false; };
  }, [creatingPdf, editBase, editing, id, owner, request]);

  useEffect(() => {
    if (owner === unassigned) return;
    let active = true;
    void readOnline(owner, request, '/categories', cachedCategories).then(({ value }) => {
      if (!active) return;
      setCategories(value);
      setCategoryError('');
    }).catch(error => { if (active) setCategoryError(errorMessage(error)); });
    return () => { active = false; };
  }, [request, owner, categoryRevision]);

  useEffect(() => {
    if (!draftId || owner === null) return;
    let active = true;
    void getJob(owner, draftId).then(draft => {
      if (!active) return;
      if (!draft) { setLoadError('Черновик больше недоступен.'); return; }
      const payload = JSON.parse(draft.payload) as Draft;
      setKind(payload.url ? 'link' : 'note');
      setUrl(payload.url ?? '');
      setTitle(payload.title ?? '');
      setNote(payload.note ?? '');
      setCategoryId(payload.category_id ?? null);
      setSelected(payload.collection_ids ?? []);
      setDraftReady(true);
    }).catch(() => { if (active) setLoadError('Не удалось прочитать черновик.'); });
    return () => { active = false; };
  }, [draftId, owner]);

  async function run(task: () => Promise<void>, describe: (error: unknown) => string = errorMessage) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try { await task(); }
    catch (error) { setMessage(describe(error)); }
    finally { locked.current = false; setBusy(false); }
  }

  async function save() {
    const cleanTitle = title.trim();
    if (creatingPdf) {
      if (!selectedPdf) { setMessage('Выберите PDF-файл.'); return; }
      await run(async () => {
        const savedId = await createPdf(request, selectedPdf, cleanTitle, categoryId);
        if (navigation.isFocused()) router.replace({ pathname: '/library/[id]', params: { id: String(savedId) } });
      }, error => {
        if (error instanceof ApiError && error.code === 'pdf_category_missing') {
          setCategoryRevision(value => value + 1);
          return 'Выбранная категория больше недоступна. Выберите другую.';
        }
        return pdfError(error, true);
      });
      return;
    }
    const cleanNote = note.trim();
    const cleanUrl = url.trim();
    if ((id === 'new' && kind === 'note' && !cleanNote) ||
      (item && item.content_type !== 'pdf' && !item.url && !cleanNote)) {
      setMessage('Введите текст заметки.');
      return;
    }
    if (id === 'new' && kind === 'link' && !cleanUrl) {
      setMessage('Введите адрес ссылки.');
      return;
    }
    if (id !== 'new' && !cleanTitle) {
      setMessage('Введите название.');
      return;
    }
    if (editBase?.url && cleanUrl !== editBase.url && !linkInput(cleanUrl)) {
      setMessage('Введите действительный адрес ссылки.');
      return;
    }
    if (cleanNote.length > 10_000 || cleanUrl.length > 2_048) {
      setMessage('Сократите ссылку или текст заметки.');
      return;
    }
    await run(async () => {
      if (id === 'new') {
        if (owner === null) throw new Error('Хранилище для этого аккаунта недоступно.');
        await enqueue(owner, {
          ...(kind === 'link' ? { url: cleanUrl } : {}),
          ...(cleanTitle ? { title: cleanTitle } : {}),
          ...(cleanNote ? { note: cleanNote } : {}),
          ...(selected.length ? { collection_ids: selected } : {}),
          category_id: categoryId,
        }, draftId);
        if (navigation.isFocused()) router.replace('/queue');
      } else if (editBase) {
        const collectionsChanged = Boolean(groups) && (selected.length !== initialCollections.length
          || selected.some(group => !initialCollections.includes(group)));
        const changes = {
          ...(title !== editBase.title ? { title: cleanTitle } : {}),
          ...(note !== (editBase.note ?? '') ? { note: cleanNote || null } : {}),
          ...(status !== editBase.status ? { status } : {}),
          ...(categoryId !== editBase.category_id ? { category_id: categoryId } : {}),
          ...(editBase.url && cleanUrl !== editBase.url ? { url: cleanUrl } : {}),
          ...(collectionsChanged ? { collection_ids: selected } : {}),
        };
        if (Object.keys(changes).length) {
          if (!editBase.version) { setMessage('Для редактирования нужна версия материала с обновлённого сервера.'); return; }
          const expected = owner ? generation(owner) : undefined;
          const saved = await request(`/contents/${id}/versioned`, 'PATCH', changes, { version: editBase.version }) as Material;
          setItem(saved);
          if (owner) void remember(owner, `/contents/${id}`, saved, expected).catch(() => {});
          setMessage('Изменения сохранены.');
        }
        setEditing(false);
      }
    }, error => {
      if (error instanceof ApiError && error.status === 412) {
        setStaleEdit(true);
        return 'Материал уже обновлён на сервере. Текущие правки можно скопировать или загрузить актуальную версию.';
      }
      if (id === 'new' && error instanceof Error) return error.message;
      if (error instanceof ApiError && error.status === 409 && error.existingId) return 'Эта ссылка уже есть в библиотеке.';
      if (error instanceof ApiError && error.code === 'collection_missing') return 'Выбранная коллекция недоступна. Отмените правки и откройте форму заново.';
      if (error instanceof ApiError && error.status === 404 && categoryId !== null && categoryId !== item?.category_id) {
        setCategoryRevision(value => value + 1);
        return 'Выбранная категория больше недоступна. Проверьте список категорий.';
      }
      return errorMessage(error, 'Проверьте адрес ссылки, название и текст заметки.');
    });
  }

  function choosePdf() {
    void run(async () => {
      await request(pdfCreatePath, 'GET');
      if (!navigation.isFocused()) return;
      const selected = await pickPdf();
      if (selected && navigation.isFocused()) setSelectedPdf(selected);
    }, error => pdfError(error, true));
  }

  function remove() {
    if (id === 'new') return;
    Alert.alert('Удалить материал?', item?.title, [
      { text: 'Отмена', style: 'cancel' },
      { text: 'Удалить', style: 'destructive', onPress: () => void run(async () => {
        try { await request(`/contents/${id}`, 'DELETE'); }
        catch (error) { if (!(error instanceof ApiError && error.status === 404 && !error.gateway)) throw error; }
        if (owner) await forgetMaterial(owner, id).catch(() => {});
        if (navigation.isFocused()) router.dismissTo('/');
      }) },
    ]);
  }

  async function openOriginal() {
    if (id === 'new' || !original) return;
    await run(async () => {
      if (cachedAt === undefined) {
        await request(`/contents/${id}/open`, 'POST');
        setItem(current => current && { ...current, open_count: current.open_count + 1 });
      }
      if (!navigation.isFocused()) return;
      try { await openURL(original); }
      catch { setMessage('Устройство не смогло открыть ссылку.'); }
    });
  }

  const categoryOptions = [{ value: null, label: 'Без категории' },
    ...categories.map(category => ({ value: category.id, label: category.name }))];
  return <Page title={id === 'new' ? 'Добавить материал' : editing ? 'Редактировать материал' : 'Материал'}
    brand={editing} subtitle={editing && id !== 'new' ? 'Обновите сведения о материале.' : undefined}>
    {id !== 'new' && !item && (loadError ? <Card>
      <Notice>{loadError}</Notice>
      <Action title="Повторить загрузку" onPress={() => { setLoadError(''); setRevision(value => value + 1); }} />
    </Card> : <Loading />)}
    {item && !editing && <Card>
      <Text accessibilityRole="header" style={styles.heading}>{item.title}</Text>
      <Body>{[item.content_type === 'pdf' ? 'PDF' : sources[item.source], statuses[item.status], categories.find(category => category.id === item.category_id)?.name].filter(Boolean).join(' · ')}</Body>
      {item.description && <Body>{item.description}</Body>}
      {item.note && <Text selectable style={styles.body}>{item.note}</Text>}
      {original && <>
        {!item.description && <Body>Описание страницы недоступно.</Body>}
        <Text selectable style={styles.body}>{original}</Text>
        <Action title="Открыть оригинал" disabled={busy} onPress={() => void openOriginal()} />
        <Body>Открытий оригинала · {item.open_count}</Body>
      </>}
      {cachedAt !== undefined && <Notice>Загруженная карточка · {new Date(cachedAt).toLocaleString('ru-RU')}</Notice>}
      <Action title="Карточки для повторения" disabled={busy || cachedAt !== undefined}
        onPress={() => router.push({ pathname: '/review', params: { id: String(item.id) } })} />
      <Action title="Добавить в недельный план" disabled={busy || cachedAt !== undefined}
        onPress={() => router.push({ pathname: '/plan', params: { id: String(item.id) } })} />
      <Action title="Теги и коллекции материала" disabled={busy || cachedAt !== undefined}
        onPress={() => router.push({ pathname: '/library/organize', params: { id: String(id) } })} />
      {item.content_type === 'pdf' && <Action title="Открыть PDF" disabled={busy || cachedAt !== undefined}
        onPress={() => router.push({ pathname: '/library/pdf', params: { id: String(id) } })} />}
      <Action title="Редактировать" disabled={busy || cachedAt !== undefined} onPress={() => beginEdit(item)} />
      <Action title="Удалить материал" disabled={busy || cachedAt !== undefined} onPress={remove} />
      {cachedAt !== undefined && <Action title="Обновить карточку" disabled={busy} onPress={() => {
        setItem(null); setLoadError(''); setRevision(value => value + 1);
      }} />}
    </Card>}
    {draftId && !draftReady && (loadError ? <Notice>{loadError}</Notice> : <Loading />)}
    {editing && draftReady && <>
      {id === 'new' && <Choice label="Вид материала" value={kind} onChange={value => { setKind(value); setMessage(''); }} disabled={busy}
        options={[{ value: 'link', label: 'Ссылка' }, { value: 'note', label: 'Заметка' },
          ...(!draftId ? [{ value: 'pdf' as const, label: 'PDF' }] : [])]} />}
      {id === 'new' && kind === 'link' && <Field label="Ссылка" value={url} onChangeText={setUrl}
        keyboardType="url" maxLength={2048} editable={!busy} />}
      {creatingPdf && <>
        <Body>{selectedPdf?.name ?? 'PDF до 10 МиБ. Для загрузки требуется подключение.'}</Body>
        <Action title={selectedPdf ? 'Выбрать другой PDF' : 'Выбрать PDF'} disabled={busy} onPress={choosePdf} />
      </>}
      <Field label={id === 'new' ? 'Название (необязательно)' : 'Название'} value={title} onChangeText={setTitle}
        maxLength={300} editable={!busy} autoCapitalize="sentences" />
      {id !== 'new' && editBase?.url && <Field label="Ссылка" value={url} onChangeText={setUrl}
        keyboardType="url" maxLength={2048} editable={!busy} />}
      {!creatingPdf && groups && <GroupSelection label="Коллекции" items={groups} selected={selected}
        onChange={setSelected} disabled={busy || Boolean(collectionError)} />}
      {!creatingPdf && collectionError && <Notice>{collectionError}</Notice>}
      {id !== 'new' && <Choice label="Статус" value={status} onChange={setStatus} disabled={busy} options={optionsOf(statuses)} />}
      {!creatingPdf && <Field label={kind === 'note' || (item && !item.url && item.content_type !== 'pdf') ? 'Текст заметки' : 'Заметка (необязательно)'}
        value={note} onChangeText={setNote} multiline maxLength={10000} editable={!busy} autoCapitalize="sentences"
        style={{ minHeight: 120, maxHeight: 250, textAlignVertical: 'top' }} />}
      {owner !== unassigned && <Choice label="Категория" value={categoryId} onChange={setCategoryId} disabled={busy} options={categoryOptions} />}
      {categoryError && <>
        <Notice>Категории не обновились. {categoryError}</Notice>
        <Action title="Обновить категории" disabled={busy} onPress={() => setCategoryRevision(value => value + 1)} />
      </>}
      <Action title={busy ? 'Сохранение…' : 'Сохранить'} disabled={busy || staleEdit || (creatingPdf && !selectedPdf)} onPress={() => void save()} />
      {staleEdit && <Action title="Загрузить актуальную версию" onPress={() => {
        setStaleEdit(false); setMessage(''); setEditing(false); setItem(null); setLoadError(''); setRevision(value => value + 1);
      }} />}
      {id !== 'new' && <Action variant="outline" title="Отменить редактирование" disabled={busy} onPress={() => {
        setEditing(false); setMessage('');
        if (staleEdit) { setStaleEdit(false); setItem(null); setLoadError(''); setRevision(value => value + 1); }
      }} />}
      {id !== 'new' && <Action variant="danger" title="Удалить материал" disabled={busy} onPress={remove} />}
    </>}
    {message && <Notice>{message}</Notice>}
  </Page>;
}
