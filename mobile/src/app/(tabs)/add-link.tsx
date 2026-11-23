import Ionicons from '@expo/vector-icons/Ionicons';
import { getStringAsync } from 'expo-clipboard';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import { GroupSelection } from '../../library/GroupSelection';
import { MaterialThumbnail } from '../../library/MaterialThumbnail';
import { linkDomain, linkInput, type Request } from '../../library/model';
import { groupPath, type Group } from '../../library/organization';
import { LibraryAccess, Notice } from '../../library/ui';
import { enqueue } from '../../offline/store';
import { colors } from '../../theme';

type Preview = { title: string | null; image_url: string | null; content_type: string };

export default function AddLink() {
  return <LibraryAccess title="Добавить ссылку" brand>{(request, owner) => <LinkForm request={request} owner={owner} />}</LibraryAccess>;
}

function LinkForm({ request, owner }: { request: Request; owner: string | null }) {
  const [url, setUrl] = useState('');
  const [note, setNote] = useState('');
  const [collections, setCollections] = useState<Group[]>();
  const [selected, setSelected] = useState<number[]>([]);
  const [preview, setPreview] = useState<{ url: string; data: Preview }>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const normalized = linkInput(url);
  const domain = linkDomain(normalized);
  const metadata = preview?.url === normalized ? preview?.data : undefined;

  useFocusEffect(useCallback(() => {
    let active = true;
    void request(groupPath('collections'), 'GET').then(value => {
      if (active) setCollections(value as Group[]);
    }).catch(() => {});
    return () => { active = false; };
  }, [request]));

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
      await enqueue(owner, { url: url.trim(), ...(note.trim() ? { note: note.trim() } : {}),
        ...(selected.length ? { collection_ids: selected } : {}) });
      setUrl('');
      setNote('');
      setSelected([]);
      setPreview(undefined);
      router.push('/queue');
    } catch {
      setMessage('Не удалось сохранить черновик на устройстве. Повторите попытку.');
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  return <Page title="Добавить ссылку" subtitle="Сохраните то, к чему хочется вернуться." brand
    footer={<>
      <Action title={busy ? 'Сохранение…' : 'Сохранить в библиотеку'} disabled={!normalized || busy || !owner} onPress={() => void save()} />
      <Text style={[styles.body, screenStyles.tip]}>Ссылки можно добавлять из меню «Поделиться».</Text>
    </>}>
    <Field label="Ссылка" placeholder="Вставьте или введите URL" value={url} onChangeText={changeUrl} keyboardType="url" maxLength={2048} editable={!busy}
      leading={<Ionicons name="link-outline" size={20} color={colors.muted} />}
      trailing={<>
        {url.length > 0 && <Pressable accessibilityRole="button" accessibilityLabel="Очистить ссылку"
          disabled={busy} onPress={() => changeUrl('')} style={screenStyles.clear}>
          <Ionicons name="close" color={colors.muted} size={19} />
        </Pressable>}
        <Action variant="text" title="Вставить" disabled={busy} onPress={() => void paste()} />
      </>} />
    <Body>Статьи, видео и другие материалы, которые вы хотите перечитать.</Body>
    {url.trim() && !normalized && <Notice>Укажите действительный адрес сайта.</Notice>}
    {message && <Notice>{message}</Notice>}
    {normalized && <>
      <Text style={styles.label}>Предпросмотр</Text>
      <Card><View style={screenStyles.preview}>
        <MaterialThumbnail imageUrl={metadata?.image_url} kind={metadata?.content_type} />
        <View style={screenStyles.details}>
          <Text style={styles.label} numberOfLines={3}>{metadata?.title ?? domain}</Text>
          {metadata?.title && <Body>{domain}</Body>}
        </View>
      </View></Card>
      {collections ? <GroupSelection label="Коллекции" items={collections} selected={selected} onChange={setSelected} disabled={busy} />
        : <Body>Для выбора коллекции подключитесь к серверу.</Body>}
      <Field label="Заметка (необязательно)" placeholder="Зачем вы сохраняете материал?" value={note} onChangeText={setNote} multiline
        maxLength={10000} editable={!busy} autoCapitalize="sentences" style={screenStyles.note} />
    </>}
    <Action variant="text" title="Добавить заметку или PDF" onPress={() => router.push('/library/new')} />
  </Page>;
}

const screenStyles = StyleSheet.create({
  tip: { textAlign: 'center', fontSize: 12 },
  clear: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  preview: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  details: { flex: 1, gap: 5 },
  note: { minHeight: 74, textAlignVertical: 'top' },
});
