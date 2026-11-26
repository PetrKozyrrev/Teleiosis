import Ionicons from '@expo/vector-icons/Ionicons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, AppState, Keyboard, Modal, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View,
  type GestureResponderEvent } from 'react-native';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import { ApiError } from '../../auth/api';
import {
  errorMessage, initialFilters, linkDomain, listPath, maxOffset, searchScopes, sorts, sources, statuses,
  type Category, type Filters, type Material, type MaterialPage, type Request, type Status,
} from '../../library/model';
import { Choice, LibraryAccess, Loading, Notice, optionsOf } from '../../library/ui';
import { cachedCategories, cachedList, forgetMaterial, readOnline, remember } from '../../offline/cache';
import { groupPath, organizationError, type Group } from '../../library/organization';
import { generation, subscribe } from '../../offline/store';
import { MaterialThumbnail } from '../../library/MaterialThumbnail';
import { PendingMaterials } from '../../library/PendingMaterials';
import { colors } from '../../theme';
import { useLocale, useTranslation } from '../../i18n';

const libraryPageSize = 10;
type ListResult = {
  query: string; revision: number; requestedOffset?: number; page?: MaterialPage; error?: string; cachedAt?: number;
};

export default function Library() {
  return <LibraryAccess brand>{(request, owner) => <LibraryList request={request} owner={owner} />}</LibraryAccess>;
}

function LibraryList({ request, owner }: { request: Request; owner: string | null }) {
  const t = useTranslation();
  const [filters, setFilters] = useState(initialFilters);
  const [offset, setOffset] = useState<number | null>(0);
  const [revision, setRevision] = useState(0);
  const [retry, setRetry] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryError, setCategoryError] = useState<{ revision: number; message: string } | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showOrganization, setShowOrganization] = useState(false);
  const [menu, setMenu] = useState<{ id: number; kind: 'item' | 'status'; x: number; y: number }>();
  const window = useWindowDimensions();
  const [mutationError, setMutationError] = useState('');
  const mutation = useRef(false);
  const seenFocus = useRef(false);
  const [groups, setGroups] = useState<{ tags: Group[]; collections: Group[] }>({ tags: [], collections: [] });
  const [groupError, setGroupError] = useState('');
  const query = listPath(filters, 0, libraryPageSize);
  const path = offset ? listPath(filters, offset, libraryPageSize) : query;
  const advancedSearch = Boolean(filters.searchIn && filters.q.trim());
  const [result, setResult] = useState<ListResult>();
  const current = result?.query === query && result.revision === revision ? result : undefined;
  const page = current?.page;
  const nextOffset = page ? page.offset + page.limit : 0;
  const loadingMore = Boolean(page && offset !== null && current?.requestedOffset !== offset);
  const filtered = Boolean(filters.q.trim() || filters.status || filters.source || filters.contentType || filters.category || filters.tag || filters.collection);

  const refresh = useCallback(() => {
    setMenu(undefined);
    setOffset(0);
    setRevision(value => value + 1);
  }, []);

  useFocusEffect(useCallback(() => {
    if (seenFocus.current) refresh();
    seenFocus.current = true;
    const listener = AppState.addEventListener('change', state => { if (state === 'active') refresh(); });
    const unsubscribe = subscribe(synced => { if (synced) refresh(); });
    return () => { listener.remove(); unsubscribe(); };
  }, [refresh]));

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
    void retry;
    if (offset === null) return;
    let active = true;
    const timer = setTimeout(() => {
      const read = advancedSearch
        ? request(path, 'GET').then(value => ({ value: value as MaterialPage, cachedAt: undefined }))
        : readOnline(owner, request, path, key => cachedList(key, filters, offset, libraryPageSize));
      void read.then(({ value: next, cachedAt }) => {
        if (!active) return;
        if (offset > 0 && next.total < offset) {
          refresh();
          return;
        }
        setResult(previous => {
          const earlier = offset > 0 && previous?.query === query && previous.revision === revision ? previous : undefined;
          const items = new Map((earlier?.page?.items ?? []).map(item => [item.id, item]));
          for (const item of next.items) items.set(item.id, item);
          return {
            query, revision, requestedOffset: offset, page: { ...next, items: [...items.values()] },
            cachedAt: cachedAt ?? earlier?.cachedAt,
          };
        });
      }).catch(error => {
        if (!active) return;
        let message = errorMessage(error);
        if (advancedSearch && error instanceof ApiError && !error.gateway) {
          if (error.status === 0) message = 'Расширенный поиск доступен при подключении к серверу.';
          if (error.status === 404) message = 'На сервере ещё недоступен расширенный поиск.';
        }
        setResult(previous => ({
          ...(offset > 0 && previous?.query === query && previous.revision === revision ? previous : undefined),
          query, revision, requestedOffset: offset, error: message,
        }));
      });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [advancedSearch, filters, offset, owner, path, query, refresh, request, retry, revision]));

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

  function loadMore() {
    setMenu(undefined);
    if (offset === nextOffset) {
      setResult(previous => previous ? { ...previous, requestedOffset: undefined, error: undefined } : previous);
      setRetry(value => value + 1);
    } else setOffset(nextOffset);
  }

  function collapseList() {
    setMenu(undefined);
    setOffset(null);
    setResult(previous => previous?.page ? {
      ...previous,
      requestedOffset: 0,
      error: undefined,
      page: { ...previous.page, offset: 0, limit: libraryPageSize, items: previous.page.items.slice(0, libraryPageSize) },
    } : previous);
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
      refresh();
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
    Alert.alert(t('Удалить материал?'), item.title, [
      { text: t('Отмена'), style: 'cancel' },
      { text: t('Удалить'), style: 'destructive', onPress: () => void runMutation(async () => {
        try { await request(`/contents/${item.id}`, 'DELETE'); }
        catch (error) { if (!(error instanceof ApiError && error.status === 404 && !error.gateway)) throw error; }
        if (owner) await forgetMaterial(owner, item.id).catch(() => {});
      }) },
    ]);
  }

  const locale = useLocale();
  const chips: { id: number | ''; name: string }[] = [
    { id: '', name: t('Все') },
    ...categories,
  ];
  const online = current?.cachedAt === undefined;
  const menuItem = online ? page?.items.find(item => item.id === menu?.id) : undefined;
  const menuWidth = Math.min(205, window.width - 24);
  const wideActions = window.width >= 600;
  const libraryActions = [
    { title: t('Управлять категориями'), icon: 'folder-outline', onPress: () => router.push('/library/categories') },
    { title: t('Теги и коллекции'), icon: 'pricetags-outline', onPress: () => router.push('/library/organization') },
    { title: t('Обновить'), icon: 'refresh-outline', onPress: refresh },
  ] as const;
  function openMenu(item: Material, kind: 'item' | 'status', event: GestureResponderEvent) {
    Keyboard.dismiss();
    setMenu({ id: item.id, kind, x: event.nativeEvent?.pageX ?? 12, y: event.nativeEvent?.pageY ?? 12 });
  }
  return <Page title={t('Библиотека')} subtitle={t('Меньше листать. Больше читать.')} brand>
    <Action title={t('Добавить')} onPress={() => router.navigate('/add-link')} />
    <View style={libraryStyles.search}>
      <View style={libraryStyles.grow}><Field hideLabel label={filters.searchIn ? t('Поисковый запрос') : t('Поиск по названию')}
        placeholder={t('Поиск по библиотеке')} leading={<Ionicons name="search-outline" size={19} color={colors.muted} />}
        value={filters.q} onChangeText={q => change({ q })} maxLength={100} returnKeyType="search" /></View>
      <Pressable accessibilityRole="button" accessibilityLabel={showFilters ? t('Скрыть фильтры') : t('Фильтры и сортировка')}
        accessibilityState={{ expanded: showFilters }} onPress={() => { setMenu(undefined); setShowFilters(!showFilters); }} style={libraryStyles.iconButton}>
        <Ionicons name="options-outline" color={colors.text} size={23} />
      </Pressable>
    </View>
    <ScrollView horizontal nestedScrollEnabled keyboardShouldPersistTaps="handled" contentContainerStyle={libraryStyles.chips}>
      {chips.map(chip => <Pressable key={chip.id} accessibilityRole="button" accessibilityLabel={chip.name}
        accessibilityState={{ selected: filters.category === chip.id }}
        style={[libraryStyles.chip, filters.category === chip.id && libraryStyles.activeChip]} onPress={() => change({ category: chip.id })}>
        <Text numberOfLines={1} style={[styles.label, filters.category === chip.id && libraryStyles.activeText]}>{chip.name}</Text>
      </Pressable>)}
    </ScrollView>
    <PendingMaterials owner={owner} />
    {showFilters && <Card>
      <Choice label={t('Искать в')} value={filters.searchIn ?? ''} onChange={searchIn => change({ searchIn })}
        options={optionsOf(searchScopes)} />
      <Choice label={t('Статус')} value={filters.status} onChange={status => change({ status })}
        options={[{ value: '', label: t('Все статусы') }, ...optionsOf(statuses)]} />
      <Choice label={t('Источник')} value={filters.source} onChange={source => change({ source })}
        options={[{ value: '', label: t('Все источники') }, ...optionsOf(sources)]} />
      <Choice label={t('Категория')} value={filters.category} onChange={category => change({ category })}
        options={[{ value: '', label: t('Все категории') }, { value: 'none', label: t('Без категории') },
          ...categories.map(category => ({ value: category.id, label: category.name }))]} />
      <Action variant="outline" title={showOrganization ? t('Скрыть теги и коллекции') : t('Фильтры по тегам и коллекциям')}
        onPress={() => setShowOrganization(!showOrganization)} />
      {showOrganization && <>
      <Choice label={t('Тег')} value={filters.tag ?? ''} onChange={tag => change({ tag })}
        options={[{ value: '', label: t('Все теги') }, ...groups.tags.map(tag => ({ value: tag.id, label: tag.name }))]} />
      <Choice label={t('Коллекция')} value={filters.collection ?? ''} onChange={collection => change({ collection })}
        options={[{ value: '', label: t('Все коллекции') }, ...groups.collections.map(collection => ({ value: collection.id, label: collection.name }))]} />
      <Body>{t('Фильтры по тегам и коллекциям работают при подключении к серверу.')}</Body>
      {groupError && <Notice>{groupError}</Notice>}
      </>}
    </Card>}
    {(filtered || filters.searchIn || filters.sort !== initialFilters.sort) &&
      <Action title={t('Сбросить поиск и фильтры')} onPress={() => change(initialFilters)} />}
    {categoryError?.revision === revision && <Notice>{t('Категории не обновились.')} {t(categoryError.message)}</Notice>}
    {!current && <Loading />}
    {current?.error && !page && <Notice>{current.error}</Notice>}
    {mutationError && <Notice>{mutationError}</Notice>}
    {current?.cachedAt !== undefined && <Notice>{t('Без подключения. Поиск среди загруженного ·')} {new Date(current.cachedAt).toLocaleString(locale)}</Notice>}
    {page && (page.items.length ? <>
      <View style={libraryStyles.counterRow}>
        <View style={libraryStyles.savedCount}>
          <Text style={styles.label}>{t('Сохранено:')} {page.total}</Text>
        </View>
        <View style={libraryStyles.sortControl}>
          <Choice label={t('Сортировка')} hideLabel value={filters.sort} onChange={sort => change({ sort })} options={optionsOf(sorts)} />
        </View>
      </View>
      {page.items.map(item => {
        const currentMenu = menu?.id === item.id ? menu.kind : undefined;
        const detail = { pathname: '/library/[id]' as const, params: { id: String(item.id) } };
        const createdAt = item.created_at ? new Date(item.created_at) : null;
        const date = createdAt && Number.isFinite(createdAt.getTime())
          ? t('Добавлено {0}', createdAt.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })) : null;
        const seconds = item.video_duration_seconds;
        let duration: string | null = null;
        if (seconds && seconds > 0) {
          duration = seconds % 60 ? t('{0} мин {1} с', Math.floor(seconds / 60), seconds % 60) : t('{0} мин', seconds / 60);
        } else if (item.reading_minutes && item.reading_minutes > 0) {
          duration = t('≈ {0} мин чтения', item.reading_minutes);
        }
        return <View key={item.id} style={libraryStyles.material}>
          <View style={libraryStyles.materialContent}>
            <Pressable accessible={false} importantForAccessibility="no"
              onPress={() => { setMenu(undefined); router.push(detail); }}>
              <MaterialThumbnail imageUrl={item.image_url} kind={item.content_type} />
            </Pressable>
            <View style={libraryStyles.grow}>
              <Pressable accessibilityRole="button" onPress={() => { setMenu(undefined); router.push(detail); }}>
                <Text style={styles.label} numberOfLines={3}>{item.title}</Text>
                <Body>{linkDomain(item.url) ?? (item.content_type === 'pdf' ? 'PDF' : t(sources[item.source]))}</Body>
                {(date || duration) && <Body>{[date, duration].filter(Boolean).join(' · ')}</Body>}
              </Pressable>
              <View style={libraryStyles.statusRow}>
                <Pressable accessibilityRole="button" accessibilityLabel={t('Статус: {0}', t(statuses[item.status]))}
                  disabled={!online || !item.version} accessibilityState={{ disabled: !online || !item.version, expanded: currentMenu === 'status' }}
                  onPress={event => openMenu(item, 'status', event)} style={[libraryStyles.status, libraryStyles[item.status]]}>
                  <Text style={[libraryStyles.statusText, item.status === 'unseen' && libraryStyles.unseenText]}>{t(statuses[item.status])}</Text>
                </Pressable>
                {item.category_id !== null && <Text style={[styles.body, libraryStyles.grow]} numberOfLines={1}>
                  {categories.find(category => category.id === item.category_id)?.name}
                </Text>}
              </View>
            </View>
          </View>
          {online && <Pressable accessibilityRole="button" accessibilityLabel={t('Действия: {0}', item.title)}
            accessibilityState={{ expanded: currentMenu === 'item' }} style={libraryStyles.more} onPress={event => openMenu(item, 'item', event)}>
            <Ionicons name="ellipsis-horizontal" color={colors.muted} size={20} />
          </Pressable>}
        </View>;
      })}
      {current?.error && <Notice>{current.error}</Notice>}
      {nextOffset < page.total && nextOffset <= maxOffset && <Action
        title={loadingMore ? t('Загрузка…') : current?.error ? t('Повторить загрузку') : t('Показать больше')}
        disabled={loadingMore} onPress={loadMore} />}
      {page.items.length > libraryPageSize && <Action variant="outline" title={t('Скрыть лишнее')} onPress={collapseList} />}
    </> : <Body>{filtered ? t('По этому запросу ничего не найдено.') : t('Библиотека пока пуста.')}</Body>)}
    <Card>
      <View style={[libraryStyles.actions, wideActions && libraryStyles.actionsGrid]}>
        {libraryActions.map(({ title, icon, onPress }) => <Pressable key={title} accessibilityRole="button" accessibilityLabel={title}
          onPress={onPress} style={({ pressed }) => [
            libraryStyles.footerAction, wideActions && libraryStyles.footerActionTile, pressed && libraryStyles.footerActionPressed,
          ]}>
          <View style={libraryStyles.footerActionIcon}>
            <Ionicons name={icon} color={colors.primary} size={19} />
          </View>
          <Text style={[styles.label, libraryStyles.footerActionLabel]}>{title}</Text>
        </Pressable>)}
      </View>
    </Card>
    {menu && menuItem && <Modal transparent statusBarTranslucent navigationBarTranslucent onRequestClose={() => setMenu(undefined)}>
      <View style={libraryStyles.menuOverlay} accessibilityViewIsModal>
        <Pressable accessibilityRole="button" accessibilityLabel={t('Закрыть меню')} style={StyleSheet.absoluteFill} onPress={() => setMenu(undefined)} />
        <View style={[libraryStyles.menu, { width: menuWidth, left: Math.max(12, Math.min(menu.x - 32, window.width - menuWidth - 12)),
          top: Math.max(12, Math.min(menu.y + 12, window.height - (menu.kind === 'item' ? 125 : 245))) }]}>
          {menu.kind === 'item' ? <>
            <Action variant="text" title={t('Редактировать')} onPress={() => {
              setMenu(undefined);
              router.push({ pathname: '/library/[id]', params: { id: String(menuItem.id), edit: '1' } });
            }} />
            <Action variant="danger" title={t('Удалить')} onPress={() => remove(menuItem)} />
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
  chips: { gap: 8 },
  chip: { minHeight: 44, maxWidth: 280, justifyContent: 'center', paddingHorizontal: 13, borderRadius: 22, backgroundColor: colors.surface },
  activeChip: { backgroundColor: colors.text },
  activeText: { color: colors.surface },
  counterRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 },
  savedCount: { maxWidth: '45%', minHeight: 48, justifyContent: 'center' },
  sortControl: { flexShrink: 1, minWidth: 0 },
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
  actions: { gap: 10 },
  actionsGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  footerAction: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 50, padding: 8,
    backgroundColor: colors.background, borderColor: colors.border, borderWidth: 1, borderRadius: 12 },
  footerActionTile: { width: '48%' },
  footerActionPressed: { backgroundColor: colors.tint },
  footerActionIcon: { width: 32, height: 32, borderRadius: 8, backgroundColor: colors.tint, alignItems: 'center', justifyContent: 'center' },
  footerActionLabel: { flex: 1 },
  more: { position: 'absolute', right: 4, top: 3, width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  menuOverlay: { flex: 1 },
  menu: { position: 'absolute', backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 10, elevation: 5, boxShadow: '0px 3px 12px #21212425' },
});
