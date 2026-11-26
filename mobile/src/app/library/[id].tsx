import { router, useFocusEffect, useLocalSearchParams, useNavigation } from 'expo-router';
import { HeaderHeightContext } from 'expo-router/react-navigation';
import { openURL } from 'expo-linking';
import { useCallback, useContext, useEffect, useRef, useState, type ComponentRef } from 'react';
import { Alert, Keyboard, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { ApiError } from '../../auth/api';
import { useAuth } from '../../auth/context';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import {
  errorMessage, linkDomain, linkInput, originalUrl, parseId, sources, statuses,
  type Category, type Material, type Request, type Status,
} from '../../library/model';
import { Choice, LibraryAccess, Loading, Notice, optionsOf } from '../../library/ui';
import { createPdf, pdfCreatePath, pdfError, pdfPath, pickPdf, removePreview, writePdfPreview, type SelectedPdf } from '../../library/pdf';
import { cachedCategories, cachedMaterial, forgetMaterial, readOnline, remember } from '../../offline/cache';
import { enqueue, generation, getJob, unassigned, type Draft } from '../../offline/store';
import { GroupSelection } from '../../library/GroupSelection';
import { groupPath, organizationPath, type Group, type Organization } from '../../library/organization';
import { MaterialThumbnail } from '../../library/MaterialThumbnail';
import { useSourceReturn } from '../../learning/sourceReturn';
import { trackLearning } from '../../learning/events';
import { colors } from '../../theme';
import { useLocale, useTranslation } from '../../i18n';

export default function MaterialRoute() {
  const t = useTranslation();
  const { id: param, draftId, inbox, edit, taskId, learningEntry, learningBudget } = useLocalSearchParams<{
    id: string; draftId?: string; inbox?: string; edit?: string; taskId?: string; learningEntry?: string; learningBudget?: string;
  }>();
  const id = param === 'new' ? 'new' : parseId(param);
  if (id === 'new' && draftId && inbox === '1') {
    return <MaterialScreen key={draftId} request={async () => { throw new ApiError(401); }} id={id} owner={unassigned} draftId={draftId} />;
  }
  return <LibraryAccess>{(request, owner) => id
    ? <MaterialScreen key={draftId ?? id} request={request} id={id} owner={owner} draftId={id === 'new' ? draftId : undefined}
      openEditor={edit === '1'} taskId={parseId(taskId)} learningEntry={learningEntry} learningBudget={learningBudget} />
    : <Page title={t('Материал')}><Notice>{t('Материал не найден.')}</Notice></Page>}
  </LibraryAccess>;
}

function MaterialScreen({ id, request, owner, draftId, openEditor, taskId, learningEntry, learningBudget }: {
  id: number | 'new'; request: Request; owner: string | null; draftId?: string; openEditor?: boolean; taskId?: number | null;
  learningEntry?: string; learningBudget?: string;
}) {
  const t = useTranslation();
  const navigation = useNavigation();
  const headerHeight = useContext(HeaderHeightContext) ?? 0;
  const formScroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const { controller } = useAuth();
  const [item, setItem] = useState<Material | null>(null);
  const [cachedAt, setCachedAt] = useState<number>();
  const [draftReady, setDraftReady] = useState(!draftId);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryError, setCategoryError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [revision, setRevision] = useState(0);
  const [categoryRevision, setCategoryRevision] = useState(0);
  const [editing, setEditing] = useState(id === 'new');
  const [showActions, setShowActions] = useState(false);
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
  const pdfPreview = useRef<ReturnType<typeof writePdfPreview> | null>(null);
  const focusRevision = useRef(0);
  const { prompt, start: watchSource, dismiss: dismissPrompt } = useSourceReturn();

  useFocusEffect(useCallback(() => () => {
    dismissPrompt();
    focusRevision.current += 1;
    removePreview(pdfPreview.current);
    pdfPreview.current = null;
  }, [dismissPrompt]));

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
    setShowActions(false);
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
        if (result.cachedAt === undefined) {
          trackLearning(request, owner, { name: 'saved_material_reopened', material_id: id });
          if (learningEntry === 'today') trackLearning(request, owner, { name: 'next_action_opened', material_id: id });
          const budget = Number(learningBudget);
          if (learningEntry === 'budget' && (budget === 5 || budget === 15 || budget === 30 || budget === 60)) {
            trackLearning(request, owner, { name: 'recommendation_opened', material_id: id, budget_minutes: budget });
          }
        }
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
  }, [beginEdit, id, learningBudget, learningEntry, owner, request, revision]));

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
        if (navigation.isFocused()) {
          if (draftId && navigation.canGoBack()) router.back();
          else router.dismissTo(owner === unassigned ? '/share-probe' : '/library');
        }
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
    Alert.alert(t('Удалить материал?'), item?.title, [
      { text: t('Отмена'), style: 'cancel' },
      { text: t('Удалить'), style: 'destructive', onPress: () => void run(async () => {
        try { await request(`/contents/${id}`, 'DELETE'); }
        catch (error) { if (!(error instanceof ApiError && error.status === 404 && !error.gateway)) throw error; }
        if (owner) await forgetMaterial(owner, id).catch(() => {});
        if (navigation.isFocused()) router.dismissTo('/library');
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
      const finish = watchSource();
      try {
        await openURL(original);
        finish(true);
      } catch {
        finish(false);
        setMessage('Устройство не смогло открыть ссылку.');
      }
    });
  }

  function openPdf() {
    if (id === 'new' || cachedAt !== undefined) return;
    const sameSession = controller.captureSession();
    const revision = focusRevision.current;
    const canOpen = () => focusRevision.current === revision && navigation.isFocused() && sameSession();
    void run(async () => {
      const data = await request(`${pdfPath(id)}/download`, 'GET') as ArrayBuffer;
      if (!canOpen()) return;
      const file = writePdfPreview(data);
      removePreview(pdfPreview.current);
      pdfPreview.current = file;
      const finish = watchSource();
      try { await file.preview(); finish(true, Platform.OS === 'ios'); }
      catch (error) {
        finish(false);
        removePreview(file);
        if (pdfPreview.current === file) pdfPreview.current = null;
        throw error;
      }
    }, error => canOpen() ? pdfError(error) : '');
  }

  function openCompletion(reflection = false) {
    if (id === 'new') return;
    dismissPrompt();
    router.push({ pathname: '/library/complete', params: {
      id: String(id), ...(reflection ? { mode: 'reflection' } : taskId ? { taskId: String(taskId) } : {}),
    } });
  }

  function revealFocusedField() {
    if (!editing || !navigation.isFocused() || !Keyboard.isVisible()) return;
    const input = TextInput.State.currentlyFocusedInput();
    if (input) formScroll.current?.scrollResponderScrollNativeHandleToKeyboard(input, headerHeight + 12, true);
  }

  const locale = useLocale();
  const categoryOptions = [{ value: null, label: t('Без категории') },
    ...categories.map(category => ({ value: category.id, label: category.name }))];
  return <Page title={id === 'new' ? t('Добавить материал') : editing ? t('Редактировать материал') : item?.title ?? t('Материал')}
    scrollRef={formScroll} keyboardOffset={editing ? headerHeight : undefined} revealFocusedField={editing ? revealFocusedField : undefined}
    brand subtitle={editing && id !== 'new' ? t('Обновите сведения о материале.') : undefined}>
    {id !== 'new' && !item && (loadError ? <Card>
      <Notice>{loadError}</Notice>
      <Action title={t('Повторить загрузку')} onPress={() => { setLoadError(''); setRevision(value => value + 1); }} />
    </Card> : <Loading />)}
    {item && !editing && <>
      <Card>
        <View style={detailStyles.overview}>
          <MaterialThumbnail imageUrl={item.image_url} kind={item.content_type} />
          <View style={detailStyles.metadata}>
            <Body>{linkDomain(item.url) ?? (item.content_type === 'pdf' ? 'PDF' : t(sources[item.source]))}</Body>
            <Text style={detailStyles.badge}>{t(statuses[item.status])}</Text>
            <Body>{categories.find(category => category.id === item.category_id)?.name}</Body>
          </View>
        </View>
        {item.description && <Text selectable style={styles.body}>{item.description}</Text>}
        {original && <>
          {!item.description && <Body>{t('Описание страницы недоступно.')}</Body>}
          <Action title={t('Открыть оригинал')} disabled={busy} onPress={() => void openOriginal()} />
        </>}
        {item.content_type === 'pdf' && <Action title={t('Открыть PDF')} disabled={busy || cachedAt !== undefined} onPress={openPdf} />}
      </Card>
      {item.note && <Card><Text style={styles.label}>{t('Заметка')}</Text><Text selectable style={styles.body}>{item.note}</Text></Card>}
      {item.status === 'studied' && <Action variant="outline" title={t('Главная мысль')} disabled={busy} onPress={() => openCompletion(true)} />}
      {(item.status !== 'studied' || taskId) && (prompt ? <Card>
        <Text accessibilityRole="header" style={styles.label}>{t('Удалось изучить?')}</Text>
        <Action title={t('Отметить изученным')} disabled={busy} onPress={() => openCompletion()} />
        <Action variant="text" title={t('Не сейчас')} onPress={dismissPrompt} />
      </Card> : <Action title={t('Отметить изученным')} disabled={busy} onPress={() => openCompletion()} />)}
      {cachedAt !== undefined && <Notice>{t('Загруженная карточка ·')} {new Date(cachedAt).toLocaleString(locale)}</Notice>}
      <Action variant="outline" title={t('Редактировать')} disabled={busy || cachedAt !== undefined} onPress={() => beginEdit(item)} />
      <Action variant="outline" title={t('Добавить к цели')} disabled={busy || cachedAt !== undefined}
        onPress={() => router.push({ pathname: '/library/goals', params: { id: String(item.id) } })} />
      <Action variant="text" title={showActions ? t('Скрыть действия') : t('Другие действия')} onPress={() => setShowActions(!showActions)} />
      {showActions && <Card>
        {original && <><Text selectable style={styles.body}>{original}</Text><Body>{t('Открытий оригинала ·')} {item.open_count}</Body></>}
        {item.status !== 'studied' && <Action variant="text" title={t('Главная мысль')} disabled={busy} onPress={() => openCompletion(true)} />}
        <Action variant="text" title={t('Карточки для повторения')} disabled={busy || cachedAt !== undefined}
          onPress={() => router.push({ pathname: '/review', params: { id: String(item.id) } })} />
        <Action variant="text" title={t('Добавить в недельный план')} disabled={busy || cachedAt !== undefined}
          onPress={() => router.push({ pathname: '/plan', params: { id: String(item.id) } })} />
        <Action variant="text" title={t('Теги и коллекции материала')} disabled={busy || cachedAt !== undefined}
          onPress={() => router.push({ pathname: '/library/organize', params: { id: String(id) } })} />
        <Action variant="danger" title={t('Удалить материал')} disabled={busy || cachedAt !== undefined} onPress={remove} />
      </Card>}
      {cachedAt !== undefined && <Action variant="outline" title={t('Обновить карточку')} disabled={busy} onPress={() => {
        setItem(null); setLoadError(''); setRevision(value => value + 1);
      }} />}
    </>}
    {draftId && !draftReady && (loadError ? <Notice>{loadError}</Notice> : <Loading />)}
    {editing && draftReady && <>
      {id === 'new' && <Choice label={t('Вид материала')} value={kind} onChange={value => { setKind(value); setMessage(''); }} disabled={busy}
        options={[{ value: 'link', label: t('Ссылка') }, { value: 'note', label: t('Заметка') },
          ...(!draftId ? [{ value: 'pdf' as const, label: 'PDF' }] : [])]} />}
      {id === 'new' && kind === 'link' && <Field label={t('Ссылка')} value={url} onChangeText={setUrl}
        keyboardType="url" maxLength={2048} editable={!busy} />}
      {creatingPdf && <>
        <Body>{selectedPdf?.name ?? t('PDF до 10 МиБ. Для загрузки требуется подключение.')}</Body>
        <Action title={selectedPdf ? t('Выбрать другой PDF') : t('Выбрать PDF')} disabled={busy} onPress={choosePdf} />
      </>}
      <Field label={id === 'new' ? t('Название (необязательно)') : t('Название')} value={title} onChangeText={setTitle}
        maxLength={300} editable={!busy} autoCapitalize="sentences" />
      {id !== 'new' && editBase?.url && <Field label={t('Ссылка')} value={url} onChangeText={setUrl}
        keyboardType="url" maxLength={2048} editable={!busy} />}
      {id !== 'new' && <Choice label={t('Статус')} value={status} onChange={setStatus} disabled={busy} options={optionsOf(statuses)} />}
      {!creatingPdf && <Field label={kind === 'note' || (item && !item.url && item.content_type !== 'pdf') ? t('Текст заметки') : t('Заметка (необязательно)')}
        value={note} onChangeText={setNote} onFocus={revealFocusedField} multiline maxLength={10000} editable={!busy} autoCapitalize="sentences"
        style={{ minHeight: 120, maxHeight: 250, textAlignVertical: 'top' }} />}
      {owner !== unassigned && <Choice label={t('Категория')} value={categoryId} onChange={setCategoryId} disabled={busy} options={categoryOptions} />}
      {!creatingPdf && groups && <GroupSelection label={t('Коллекции (необязательно)')} items={groups} selected={selected}
        onChange={setSelected} disabled={busy || Boolean(collectionError)} />}
      {!creatingPdf && collectionError && <Notice>{collectionError}</Notice>}
      {categoryError && <>
        <Notice>{t('Категории не обновились.')} {t(categoryError)}</Notice>
        <Action title={t('Обновить категории')} disabled={busy} onPress={() => setCategoryRevision(value => value + 1)} />
      </>}
      <Action title={busy ? t('Сохранение…') : t('Сохранить')} disabled={busy || staleEdit || (creatingPdf && !selectedPdf)} onPress={() => void save()} />
      {staleEdit && <Action title={t('Загрузить актуальную версию')} onPress={() => {
        setStaleEdit(false); setMessage(''); setEditing(false); setItem(null); setLoadError(''); setRevision(value => value + 1);
      }} />}
      {id !== 'new' && <Action variant="outline" title={t('Отменить редактирование')} disabled={busy} onPress={() => {
        setEditing(false); setMessage('');
        if (staleEdit) { setStaleEdit(false); setItem(null); setLoadError(''); setRevision(value => value + 1); }
      }} />}
      {id !== 'new' && <Action variant="danger" title={t('Удалить материал')} disabled={busy} onPress={remove} />}
    </>}
    {message && <Notice>{message}</Notice>}
  </Page>;
}

const detailStyles = StyleSheet.create({
  overview: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  metadata: { flex: 1, gap: 4 },
  badge: { ...styles.label, backgroundColor: colors.tint, color: colors.primary, paddingVertical: 4, paddingHorizontal: 8, borderRadius: 6, alignSelf: 'flex-start' },
});
