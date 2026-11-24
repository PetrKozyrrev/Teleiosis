import Ionicons from '@expo/vector-icons/Ionicons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState, type ComponentRef } from 'react';
import { Alert, AppState, Keyboard, Modal, Pressable, StyleSheet, Text, useWindowDimensions, View,
  type GestureResponderEvent, type ScrollView } from 'react-native';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import { ApiError } from '../../auth/api';
import {
  errorMessage, initialFilters, linkDomain, listPath, maxOffset, pageSize, searchScopes, sorts, sources, statuses,
  type Category, type Filters, type Material, type MaterialPage, type Request, type Status,
} from '../../library/model';
import { Choice, LibraryAccess, Loading, Notice, optionsOf } from '../../library/ui';
import { cachedCategories, cachedList, forgetMaterial, readOnline, remember } from '../../offline/cache';
import { groupPath, organizationError, type Group } from '../../library/organization';
import { generation, subscribe } from '../../offline/store';
import { MaterialThumbnail } from '../../library/MaterialThumbnail';
import { colors } from '../../theme';

export default function Library() {
  return <LibraryAccess brand>{(request, owner) => <LibraryList request={request} owner={owner} />}</LibraryAccess>;
}

function LibraryList({ request, owner }: { request: Request; owner: string | null }) {
  const [filters, setFilters] = useState(initialFilters);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryError, setCategoryError] = useState<{ revision: number; message: string } | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showOrganization, setShowOrganization] = useState(false);
  const [menu, setMenu] = useState<{ id: number; kind: 'item' | 'status'; x: number; y: number }>();
  const window = useWindowDimensions();
  const [mutationError, setMutationError] = useState('');
  const mutation = useRef(false);
  const [groups, setGroups] = useState<{ tags: Group[]; collections: Group[] }>({ tags: [], collections: [] });
  const [groupError, setGroupError] = useState('');
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);
  const path = listPath(filters, offset);
  const advancedSearch = Boolean(filters.searchIn && filters.q.trim());
  const [result, setResult] = useState<{ path: string; revision: number; page?: MaterialPage; error?: string; cachedAt?: number }>();
  const current = result?.path === path && result.revision === revision ? result : undefined;
  const page = current?.page;
  const filtered = Boolean(filters.q.trim() || filters.status || filters.source || filters.contentType || filters.category || filters.tag || filters.collection);

  useFocusEffect(useCallback(() => {
    const refresh = () => setRevision(value => value + 1);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') refresh(); });
    const unsubscribe = subscribe(synced => { if (synced) refresh(); });
    return () => { listener.remove(); unsubscribe(); };
  }, []));

  useFocusEffect(useCallback(() => {
    let active = true;
    void readOnline(owner, request, '/categories', cachedCategories).then(({ value }) => {
      if (!active) return;
      setCategories(value);
      setCategoryError(null);
    }).catch(error => { if (active) setCategoryError({ revision, message: errorMessage(error) }); });
    return () => { active = false; };
  }, [owner, request, revision]));

  useFocusEffect(useCallback(() => {
    let active = true;
    const timer = setTimeout(() => {
      const read = advancedSearch
        ? request(path, 'GET').then(value => ({ value: value as MaterialPage, cachedAt: undefined }))
        : readOnline(owner, request, path, key => cachedList(key, filters, offset));
      void read.then(({ value: next, cachedAt }) => {
        if (!active) return;
        const lastOffset = Math.max(0, Math.floor((next.total - 1) / pageSize) * pageSize);
        if (!next.items.length && offset > lastOffset) setOffset(lastOffset);
        else setResult({ path, revision, page: next, cachedAt });
      }).catch(error => {
        if (!active) return;
        let message = errorMessage(error);
        if (advancedSearch && error instanceof ApiError && !error.gateway) {
          if (error.status === 0) message = 'Расширенный поиск доступен при подключении к серверу.';
          if (error.status === 404) message = 'На сервере ещё недоступен расширенный поиск.';
        }
        setResult({ path, revision, error: message });
      });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [advancedSearch, filters, offset, owner, path, request, revision]));

  useFocusEffect(useCallback(() => {
    void revision; // Refresh available groups together with the list.
    if (!showFilters || !showOrganization) return;
    let active = true;
    void Promise.all([request(groupPath('tags'), 'GET'), request(groupPath('collections'), 'GET')]).then(([tags, collections]) => {
      if (active) { setGroups({ tags: tags as Group[], collections: collections as Group[] }); setGroupError(''); }
    }).catch(error => { if (active) setGroupError(organizationError(error, true)); });
    return () => { active = false; };
  }, [showFilters, showOrganization, request, revision]));

  function change(next: Partial<Filters>) {
    setMenu(undefined);
    setResult(undefined);
    setFilters(currentFilters => ({ ...currentFilters, ...next }));
    setOffset(0);
  }

  function goToPage(nextOffset: number) {
    setMenu(undefined);
    setResult(undefined);
    scrollRef.current?.scrollTo({ y: 0, animated: false });
    setOffset(nextOffset);
  }

  async function runMutation(task: () => Promise<void>) {
    if (mutation.current) return;
    mutation.current = true;
    setMenu(undefined);
    setMutationError('');
    try { await task(); }
    catch (error) {
      setMutationError(error instanceof ApiError && error.status === 412
        ? 'Материал уже изменился. Список обновлён.' : errorMessage(error));
    } finally {
      setRevision(value => value + 1);
      mutation.current = false;
    }
  }

  function changeStatus(item: Material, status: Status) {
    if (!item.version || item.status === status) { setMenu(undefined); return; }
    const expected = owner ? generation(owner) : undefined;
    void runMutation(async () => {
      const updated = await request(`/contents/${item.id}/versioned`, 'PATCH', { status }, { version: item.version });
      if (owner) await remember(owner, `/contents/${item.id}`, updated, expected).catch(() => {});
    });
  }

  function remove(item: Material) {
    setMenu(undefined);
    Alert.alert('Удалить материал?', item.title, [
      { text: 'Отмена', style: 'cancel' },
      { text: 'Удалить', style: 'destructive', onPress: () => void runMutation(async () => {
        try { await request(`/contents/${item.id}`, 'DELETE'); }
        catch (error) { if (!(error instanceof ApiError && error.status === 404 && !error.gateway)) throw error; }
        if (owner) await forgetMaterial(owner, item.id).catch(() => {});
      }) },
    ]);
  }

  const chips: { id: number | ''; name: string }[] = [
    { id: '', name: 'Все' },
    ...categories,
  ];
  const online = current?.cachedAt === undefined;
  const menuItem = online ? page?.items.find(item => item.id === menu?.id) : undefined;
  const menuWidth = Math.min(205, window.width - 24);
  function openMenu(item: Material, kind: 'item' | 'status', event: GestureResponderEvent) {
    Keyboard.dismiss();
    setMenu({ id: item.id, kind, x: event.nativeEvent?.pageX ?? 12, y: event.nativeEvent?.pageY ?? 12 });
  }
  return <Page title="Библиотека" subtitle="Меньше листать. Больше читать." brand scrollRef={scrollRef}>
    <View style={libraryStyles.search}>
      <View style={libraryStyles.grow}><Field hideLabel label={filters.searchIn ? 'Поисковый запрос' : 'Поиск по названию'}
        placeholder="Поиск по библиотеке" leading={<Ionicons name="search-outline" size={19} color={colors.muted} />}
        value={filters.q} onChangeText={q => change({ q })} maxLength={100} returnKeyType="search" /></View>
      <Pressable accessibilityRole="button" accessibilityLabel={showFilters ? 'Скрыть фильтры' : 'Фильтры и сортировка'}
        accessibilityState={{ expanded: showFilters }} onPress={() => { setMenu(undefined); setShowFilters(!showFilters); }} style={libraryStyles.iconButton}>
        <Ionicons name="options-outline" color={colors.text} size={23} />
      </Pressable>
    </View>
    <View style={libraryStyles.chips}>
      {chips.map(chip => <Pressable key={chip.id} accessibilityRole="button" accessibilityState={{ selected: filters.category === chip.id }}
        style={[libraryStyles.chip, filters.category === chip.id && libraryStyles.activeChip]} onPress={() => change({ category: chip.id })}>
        <Text style={[styles.label, filters.category === chip.id && libraryStyles.activeText]}>{chip.name}</Text>
      </Pressable>)}
    </View>
    {showFilters && <Card>
      <Choice label="Искать в" value={filters.searchIn ?? ''} onChange={searchIn => change({ searchIn })}
        options={optionsOf(searchScopes)} />
      <Choice label="Статус" value={filters.status} onChange={status => change({ status })}
        options={[{ value: '', label: 'Все статусы' }, ...optionsOf(statuses)]} />
      <Choice label="Источник" value={filters.source} onChange={source => change({ source })}
        options={[{ value: '', label: 'Все источники' }, ...optionsOf(sources)]} />
      <Choice label="Категория" value={filters.category} onChange={category => change({ category })}
        options={[{ value: '', label: 'Все категории' }, { value: 'none', label: 'Без категории' },
          ...categories.map(category => ({ value: category.id, label: category.name }))]} />
      <Action variant="outline" title={showOrganization ? 'Скрыть теги и коллекции' : 'Фильтры по тегам и коллекциям'}
        onPress={() => setShowOrganization(!showOrganization)} />
      {showOrganization && <>
      <Choice label="Тег" value={filters.tag ?? ''} onChange={tag => change({ tag })}
        options={[{ value: '', label: 'Все теги' }, ...groups.tags.map(tag => ({ value: tag.id, label: tag.name }))]} />
      <Choice label="Коллекция" value={filters.collection ?? ''} onChange={collection => change({ collection })}
        options={[{ value: '', label: 'Все коллекции' }, ...groups.collections.map(collection => ({ value: collection.id, label: collection.name }))]} />
      <Body>Фильтры по тегам и коллекциям работают при подключении к серверу.</Body>
      {groupError && <Notice>{groupError}</Notice>}
      </>}
    </Card>}
    {(filtered || filters.searchIn || filters.sort !== initialFilters.sort) &&
      <Action title="Сбросить поиск и фильтры" onPress={() => change(initialFilters)} />}
    {categoryError?.revision === revision && <Notice>Категории не обновились. {categoryError.message}</Notice>}
    {!current && <Loading />}
    {current?.error && <Notice>{current.error}</Notice>}
    {mutationError && <Notice>{mutationError}</Notice>}
    {current?.cachedAt !== undefined && <Notice>Без подключения. Поиск среди загруженного · {new Date(current.cachedAt).toLocaleString('ru-RU')}</Notice>}
    {page && (page.items.length ? <>
      <View style={libraryStyles.counterRow}>
        <Text style={styles.label}>Сохранено: {page.total}</Text>
        <Choice label="Сортировка" value={filters.sort} onChange={sort => change({ sort })} options={optionsOf(sorts)} />
      </View>
      {page.items.map(item => {
        const currentMenu = menu?.id === item.id ? menu.kind : undefined;
        const detail = { pathname: '/library/[id]' as const, params: { id: String(item.id) } };
        return <View key={item.id} style={libraryStyles.material}>
          <View style={libraryStyles.materialContent}>
            <Pressable accessible={false} importantForAccessibility="no"
              onPress={() => { setMenu(undefined); router.push(detail); }}>
              <MaterialThumbnail imageUrl={item.image_url} kind={item.content_type} />
            </Pressable>
            <View style={libraryStyles.grow}>
              <Pressable accessibilityRole="button" onPress={() => { setMenu(undefined); router.push(detail); }}>
                <Text style={styles.label} numberOfLines={3}>{item.title}</Text>
                <Body>{linkDomain(item.url) ?? (item.content_type === 'pdf' ? 'PDF' : sources[item.source])}</Body>
              </Pressable>
              <View style={libraryStyles.statusRow}>
                <Pressable accessibilityRole="button" accessibilityLabel={`Статус: ${statuses[item.status]}`}
                  disabled={!online || !item.version} accessibilityState={{ disabled: !online || !item.version, expanded: currentMenu === 'status' }}
                  onPress={event => openMenu(item, 'status', event)} style={[libraryStyles.status, libraryStyles[item.status]]}>
                  <Text style={[libraryStyles.statusText, item.status === 'unseen' && libraryStyles.unseenText]}>{statuses[item.status]}</Text>
                </Pressable>
                {item.category_id !== null && <Text style={[styles.body, libraryStyles.grow]} numberOfLines={1}>
                  {categories.find(category => category.id === item.category_id)?.name}
                </Text>}
              </View>
            </View>
          </View>
          {online && <Pressable accessibilityRole="button" accessibilityLabel={`Действия: ${item.title}`}
            accessibilityState={{ expanded: currentMenu === 'item' }} style={libraryStyles.more} onPress={event => openMenu(item, 'item', event)}>
            <Ionicons name="ellipsis-horizontal" color={colors.muted} size={20} />
          </Pressable>}
        </View>;
      })}
      {offset > 0 && <Action title="Предыдущая страница" onPress={() => goToPage(offset - pageSize)} />}
      {offset + page.limit < page.total && offset + pageSize <= maxOffset &&
        <Action title="Следующая страница" onPress={() => goToPage(offset + pageSize)} />}
    </> : <Body>{filtered ? 'По этому запросу ничего не найдено.' : 'Библиотека пока пуста.'}</Body>)}
    <View style={libraryStyles.chips}>
      <Action variant="text" title="Управлять категориями" onPress={() => router.push('/library/categories')} />
      <Action variant="text" title="Теги и коллекции" onPress={() => router.push('/library/organization')} />
      <Action variant="text" title="Отправка и входящие" onPress={() => router.push('/queue')} />
      <Action variant="text" title="Обновить" onPress={() => setRevision(value => value + 1)} />
    </View>
    {menu && menuItem && <Modal transparent statusBarTranslucent navigationBarTranslucent onRequestClose={() => setMenu(undefined)}>
      <View style={libraryStyles.menuOverlay} accessibilityViewIsModal>
        <Pressable accessibilityRole="button" accessibilityLabel="Закрыть меню" style={StyleSheet.absoluteFill} onPress={() => setMenu(undefined)} />
        <View style={[libraryStyles.menu, { width: menuWidth, left: Math.max(12, Math.min(menu.x - 32, window.width - menuWidth - 12)),
          top: Math.max(12, Math.min(menu.y + 12, window.height - (menu.kind === 'item' ? 125 : 245))) }]}>
          {menu.kind === 'item' ? <>
            <Action variant="text" title="Редактировать" onPress={() => {
              setMenu(undefined);
              router.push({ pathname: '/library/[id]', params: { id: String(menuItem.id), edit: '1' } });
            }} />
            <Action variant="danger" title="Удалить" onPress={() => remove(menuItem)} />
          </> : optionsOf(statuses).map(({ value, label }) =>
            <Action key={value} variant="text" title={label} onPress={() => changeStatus(menuItem, value)} />)}
        </View>
      </View>
    </Modal>}
  </Page>;
}

const libraryStyles = StyleSheet.create({
  grow: { flex: 1 },
  search: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  iconButton: { width: 48, height: 48, borderRadius: 12, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 13, borderRadius: 22, backgroundColor: colors.surface },
  activeChip: { backgroundColor: colors.text },
  activeText: { color: colors.surface },
  counterRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 },
  material: { position: 'relative', borderRadius: 16, backgroundColor: colors.surface, padding: 12, gap: 3 },
  materialContent: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingRight: 34 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3 },
  status: { minHeight: 32, borderRadius: 8, paddingHorizontal: 8, justifyContent: 'center' },
  unseen: { backgroundColor: colors.tint },
  planned: { backgroundColor: colors.coolTint },
  studied: { backgroundColor: colors.greenTint },
  irrelevant: { backgroundColor: colors.background },
  statusText: { ...styles.label, fontSize: 12 },
  unseenText: { color: colors.primary },
  more: { position: 'absolute', right: 4, top: 3, width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  menuOverlay: { flex: 1 },
  menu: { position: 'absolute', backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 10, elevation: 5, boxShadow: '0px 3px 12px #21212425' },
});
