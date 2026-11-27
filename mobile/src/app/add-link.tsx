import Ionicons from '@expo/vector-icons/Ionicons';
import { getStringAsync } from 'expo-clipboard';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Action, Body, Card, Field, Page, styles } from '../components/ui';
import { cachedCategories, readOnline } from '../offline/cache';
import { GroupSelection } from '../library/GroupSelection';
import { MaterialThumbnail } from '../library/MaterialThumbnail';
import { PendingMaterialActions, PendingMaterials } from '../library/PendingMaterials';
import { linkDomain, linkInput, type Category, type Request } from '../library/model';
import { groupPath, type Group } from '../library/organization';
import { Choice, LibraryAccess, Notice } from '../library/ui';
import { enqueue, getJob, subscribe, type Job } from '../offline/store';
import { colors } from '../theme';
import { useTranslation } from '../i18n';

type Preview = { title: string | null; image_url: string | null; content_type: string };
const successNoticeDuration = 5_000;

export default function AddLink() {
  const t = useTranslation();
  return <LibraryAccess title={t('Добавить материал')} brand>{(request, owner) => <LinkForm request={request} owner={owner} />}</LibraryAccess>;
}

function LinkForm({ request, owner }: { request: Request; owner: string | null }) {
  const t = useTranslation();
  const [url, setUrl] = useState('');
  const [note, setNote] = useState('');
  const [collections, setCollections] = useState<Group[]>();
  const [selected, setSelected] = useState<number[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [category, setCategory] = useState<number | null>(null);
  const [showCollections, setShowCollections] = useState(false);
  const [preview, setPreview] = useState<{ url: string; data: Preview }>();
  const [message, setMessage] = useState('');
  const [submission, setSubmission] = useState<string>();
  const [job, setJob] = useState<Job | null>();
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const normalized = linkInput(url);
  const domain = linkDomain(normalized);
  const metadata = preview?.url === normalized ? preview?.data : undefined;
  const confirmedSubmission = job?.state === 'synced' ? submission : undefined;

  useFocusEffect(useCallback(() => {
    let active = true;
    void readOnline(owner, request, '/categories', cachedCategories).then(({ value }) => {
      if (active && Array.isArray(value)) setCategories(value);
    }).catch(() => {});
    return () => { active = false; };
  }, [request, owner]));

  useEffect(() => {
    if (!showCollections) return;
    let active = true;
    void request(groupPath('collections'), 'GET').then(value => {
      if (active) setCollections(value as Group[]);
    }).catch(() => {});
    return () => { active = false; };
  }, [request, showCollections]);

  useFocusEffect(useCallback(() => {
    if (!owner || !submission) return;
    let revision = 0;
    function update() {
      const current = ++revision;
      void getJob(owner!, submission!).then(next => {
        if (revision === current) setJob(next);
      }).catch(() => {});
    }
    const unsubscribe = subscribe(update);
    update();
    return () => { revision += 1; unsubscribe(); };
  }, [owner, submission]));

  useFocusEffect(useCallback(() => {
    if (!confirmedSubmission) return;
    const dismiss = () => setSubmission(current => current === confirmedSubmission ? undefined : current);
    const timer = setTimeout(dismiss, successNoticeDuration);
    return () => {
      clearTimeout(timer);
      dismiss();
    };
  }, [confirmedSubmission]));

  useEffect(() => {
    if (!normalized || preview?.url === normalized) return;
    let active = true;
    const timer = setTimeout(() => {
      void request('/mobile/library/link-preview', 'POST', { url: normalized }).then(data => {
        if (active) setPreview({ url: normalized, data: data as Preview });
      }).catch(() => {});
    }, 700);
    return () => { active = false; clearTimeout(timer); };
  }, [normalized, preview?.url, request]);

  function changeUrl(value: string) {
    setUrl(value);
    setMessage('');
    setSubmission(undefined);
    setJob(undefined);
  }

  async function paste() {
    try {
      const value = (await getStringAsync()).trim();
      if (linkInput(value)) changeUrl(value);
      else setMessage('Скопируйте ссылку из браузера и повторите.');
    } catch {
      setMessage('Не удалось прочитать буфер обмена.');
    }
  }

  async function save() {
    if (!normalized || !owner || locked.current) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try {
      const id = await enqueue(owner, { url: url.trim(), ...(note.trim() ? { note: note.trim() } : {}),
        ...(category !== null ? { category_id: category } : {}),
        ...(selected.length ? { collection_ids: selected } : {}) });
      setUrl('');
      setNote('');
      setSelected([]);
      setCategory(null);
      setPreview(undefined);
      setJob(undefined);
      setSubmission(id);
    } catch {
      setMessage('Не удалось сохранить черновик на устройстве. Повторите попытку.');
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  return <Page title={t('Добавить материал')} brand insetFooter
    footer={<>
      <Action title={busy ? t('Сохранение…') : t('Сохранить в библиотеку')} disabled={!normalized || busy || !owner} onPress={() => void save()} />
      <Text style={[styles.body, screenStyles.tip]}>{t('Ссылки можно добавлять из меню «Поделиться».')}</Text>
    </>}>
    <View style={screenStyles.kinds}>
      <Action variant="outline" title={t('Заметка')} style={screenStyles.kind}
        onPress={() => router.push({ pathname: '/library/[id]', params: { id: 'new', kind: 'note' } })} />
      <Action variant="outline" title="PDF" style={screenStyles.kind}
        onPress={() => router.push({ pathname: '/library/[id]', params: { id: 'new', kind: 'pdf' } })} />
    </View>
    <Field label={t('Ссылка')} placeholder={t('Вставьте или введите URL')} value={url} onChangeText={changeUrl} keyboardType="url" maxLength={2048} editable={!busy}
      leading={<Ionicons name="link-outline" size={20} color={colors.muted} />}
      trailing={<>
        {url.length > 0 && <Pressable accessibilityRole="button" accessibilityLabel={t('Очистить ссылку')}
          disabled={busy} onPress={() => changeUrl('')} style={screenStyles.clear}>
          <Ionicons name="close" color={colors.muted} size={19} />
        </Pressable>}
        <Action variant="text" title={t('Вставить')} disabled={busy} onPress={() => void paste()} />
      </>} />
    <Body>{t('Статьи, видео и другие материалы, которые вы хотите перечитать.')}</Body>
    {url.trim() && !normalized && <Notice>{t('Укажите действительный адрес сайта.')}</Notice>}
    {message && <Notice>{t(message)}</Notice>}
    {submission && <Card>
      <Notice>{job?.state === 'synced' ? t('Ссылка добавлена в библиотеку.')
        : job?.reason === 'duplicate' ? t('Эта ссылка уже есть в библиотеке.')
        : job?.state === 'needs_action' ? t('Ссылка сохранена на устройстве. Для отправки нужно действие.')
        : t('Ссылка сохранена на устройстве и появится в библиотеке после отправки.')}</Notice>
      {job?.state === 'needs_action' && job.reason !== 'duplicate'
        ? <PendingMaterialActions job={job} owner={owner} onDiscarded={() => setSubmission(undefined)} />
        : <Action variant="text" title={t('Открыть библиотеку')} onPress={() => {
          if (confirmedSubmission) setSubmission(undefined);
          router.navigate('/library');
        }} />}
    </Card>}
    {job?.state === 'synced' && job.server_id !== null && <Action variant="text" title={t('Добавить к цели')}
      onPress={() => router.push({ pathname: '/library/goals', params: { id: String(job.server_id) } })} />}
    {normalized && <>
      <Text style={styles.label}>{t('Предпросмотр')}</Text>
      <Card><View style={screenStyles.preview}>
        <MaterialThumbnail imageUrl={metadata?.image_url} kind={metadata?.content_type} />
        <View style={screenStyles.details}>
          <Text style={styles.label} numberOfLines={3}>{metadata?.title ?? domain}</Text>
          {metadata?.title && <Body>{domain}</Body>}
        </View>
      </View></Card>
      <Choice label={t('Категория')} value={category} onChange={setCategory} disabled={busy}
        options={[{ value: null, label: t('Без категории') }, ...categories.map(item => ({ value: item.id, label: item.name }))]} />
      <Action variant="text" title={showCollections ? t('Скрыть коллекции') : t('Добавить в подборку')} disabled={busy}
        onPress={() => setShowCollections(!showCollections)} />
      {showCollections && (collections ? <GroupSelection label={t('Коллекции')} items={collections} selected={selected} onChange={setSelected} disabled={busy} />
        : <Body>{t('Для выбора коллекции подключитесь к серверу.')}</Body>)}
      <Field label={t('Заметка (необязательно)')} placeholder={t('Зачем вы сохраняете материал?')} value={note} onChangeText={setNote} multiline
        maxLength={10000} editable={!busy} autoCapitalize="sentences" style={screenStyles.note} />
    </>}
    <PendingMaterials owner={owner} failuresOnly excludeId={job?.reason === 'duplicate' ? undefined : submission} />
  </Page>;
}

const screenStyles = StyleSheet.create({
  kinds: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  kind: { flexGrow: 1 },
  tip: { textAlign: 'center', fontSize: 12 },
  clear: { minWidth: 48, minHeight: 48, alignItems: 'center', justifyContent: 'center' },
  preview: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  details: { flex: 1, gap: 5 },
  note: { minHeight: 74, textAlignVertical: 'top' },
});
