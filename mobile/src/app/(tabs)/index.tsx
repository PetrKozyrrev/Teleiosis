import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState, type ComponentRef } from 'react';
import { AppState, Pressable, Text, type ScrollView } from 'react-native';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import {
  errorMessage, initialFilters, listPath, maxOffset, pageSize, sorts, sources, statuses,
  type Category, type Filters, type MaterialPage, type Request,
} from '../../library/model';
import { Choice, LibraryAccess, Loading, Notice, optionsOf } from '../../library/ui';
import { cachedCategories, cachedList, readOnline } from '../../offline/cache';
import { groupPath, organizationError, type Group } from '../../library/organization';
import { subscribe } from '../../offline/store';

export default function Library() {
  return <LibraryAccess>{(request, owner) => <LibraryList request={request} owner={owner} />}</LibraryAccess>;
}

function LibraryList({ request, owner }: { request: Request; owner: string | null }) {
  const [filters, setFilters] = useState(initialFilters);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryError, setCategoryError] = useState<{ revision: number; message: string } | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [groups, setGroups] = useState<{ tags: Group[]; collections: Group[] }>({ tags: [], collections: [] });
  const [groupError, setGroupError] = useState('');
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);
  const path = listPath(filters, offset);
  const [result, setResult] = useState<{ path: string; revision: number; page?: MaterialPage; error?: string; cachedAt?: number }>();
  const current = result?.path === path && result.revision === revision ? result : undefined;
  const page = current?.page;
  const filtered = Boolean(filters.q.trim() || filters.status || filters.source || filters.category || filters.tag || filters.collection);

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
      void readOnline(owner, request, path, key => cachedList(key, filters, offset)).then(({ value: next, cachedAt }) => {
        if (!active) return;
        const lastOffset = Math.max(0, Math.floor((next.total - 1) / pageSize) * pageSize);
        if (!next.items.length && offset > lastOffset) setOffset(lastOffset);
        else setResult({ path, revision, page: next, cachedAt });
      }).catch(error => {
        if (active) setResult({ path, revision, error: errorMessage(error) });
      });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [filters, offset, owner, path, request, revision]));

  useFocusEffect(useCallback(() => {
    void revision; // Refresh available groups together with the list.
    if (!showFilters) return;
    let active = true;
    void Promise.all([request(groupPath('tags'), 'GET'), request(groupPath('collections'), 'GET')]).then(([tags, collections]) => {
      if (active) { setGroups({ tags: tags as Group[], collections: collections as Group[] }); setGroupError(''); }
    }).catch(error => { if (active) setGroupError(organizationError(error, true)); });
    return () => { active = false; };
  }, [showFilters, request, revision]));

  function change(next: Partial<Filters>) {
    setFilters(currentFilters => ({ ...currentFilters, ...next }));
    setOffset(0);
  }

  function goToPage(nextOffset: number) {
    scrollRef.current?.scrollTo({ y: 0, animated: false });
    setOffset(nextOffset);
  }

  return <Page title="Библиотека" scrollRef={scrollRef}>
    <Action title="Добавить материал" onPress={() => router.push('/library/new')} />
    <Action title="Управлять категориями" onPress={() => router.push('/library/categories')} />
    <Action title="Теги и коллекции" onPress={() => router.push('/library/organization')} />
    <Action title="Очередь и входящие" onPress={() => router.push('/queue')} />
    <Field label="Поиск по названию" value={filters.q} onChangeText={q => change({ q })} maxLength={100} returnKeyType="search" />
    <Action title={showFilters ? 'Скрыть фильтры' : 'Фильтры и сортировка'} onPress={() => setShowFilters(!showFilters)} />
    {showFilters && <Card>
      <Choice label="Статус" value={filters.status} onChange={status => change({ status })}
        options={[{ value: '', label: 'Все статусы' }, ...optionsOf(statuses)]} />
      <Choice label="Источник" value={filters.source} onChange={source => change({ source })}
        options={[{ value: '', label: 'Все источники' }, ...optionsOf(sources)]} />
      <Choice label="Категория" value={filters.category} onChange={category => change({ category })}
        options={[{ value: '', label: 'Все категории' }, { value: 'none', label: 'Без категории' },
          ...categories.map(category => ({ value: category.id, label: category.name }))]} />
      <Choice label="Тег" value={filters.tag ?? ''} onChange={tag => change({ tag })}
        options={[{ value: '', label: 'Все теги' }, ...groups.tags.map(tag => ({ value: tag.id, label: tag.name }))]} />
      <Choice label="Коллекция" value={filters.collection ?? ''} onChange={collection => change({ collection })}
        options={[{ value: '', label: 'Все коллекции' }, ...groups.collections.map(collection => ({ value: collection.id, label: collection.name }))]} />
      <Body>Фильтры по тегам и коллекциям работают при подключении к серверу.</Body>
      {groupError && <Notice>{groupError}</Notice>}
      <Choice label="Сортировка" value={filters.sort} onChange={sort => change({ sort })} options={optionsOf(sorts)} />
    </Card>}
    {(filtered || filters.sort !== initialFilters.sort) &&
      <Action title="Сбросить поиск и фильтры" onPress={() => change(initialFilters)} />}
    {categoryError?.revision === revision && <Notice>Категории не обновились. {categoryError.message}</Notice>}
    <Action title="Обновить" onPress={() => setRevision(value => value + 1)} />
    {!current && <Loading />}
    {current?.error && <Notice>{current.error}</Notice>}
    {current?.cachedAt !== undefined && <Notice>Без подключения. Поиск среди загруженного · {new Date(current.cachedAt).toLocaleString('ru-RU')}</Notice>}
    {page && (page.items.length ? <>
      <Notice>{offset + 1}–{offset + page.items.length} из {page.total}</Notice>
      {page.items.map(item => <Pressable key={item.id} accessibilityRole="button" style={styles.card}
        onPress={() => router.push({ pathname: '/library/[id]', params: { id: String(item.id) } })}>
        <Text style={styles.heading} numberOfLines={3}>{item.title}</Text>
        <Body>{[sources[item.source], statuses[item.status], categories.find(category => category.id === item.category_id)?.name].filter(Boolean).join(' · ')}</Body>
      </Pressable>)}
      {offset > 0 && <Action title="Предыдущая страница" onPress={() => goToPage(offset - pageSize)} />}
      {offset + page.limit < page.total && offset + pageSize <= maxOffset &&
        <Action title="Следующая страница" onPress={() => goToPage(offset + pageSize)} />}
    </> : <Body>{filtered ? 'По этому запросу ничего не найдено.' : 'Библиотека пока пуста.'}</Body>)}
  </Page>;
}
