import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { Alert, Text, type ScrollView } from 'react-native';
import { ApiError } from '../../auth/api';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import { errorMessage, uncertainCreate, type Category, type Request } from '../../library/model';
import { LibraryAccess, Loading, Notice, RenameAction } from '../../library/ui';
import { useTranslation } from '../../i18n';

export default function CategoriesRoute() {
  return <LibraryAccess>{request => <Categories request={request} />}</LibraryAccess>;
}

function Categories({ request }: { request: Request }) {
  const t = useTranslation();
  const [items, setItems] = useState<Category[] | null>(null);
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<Category | null>(null);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);

  useEffect(() => {
    let active = true;
    void request('/categories', 'GET').then(value => {
      if (!active) return;
      setItems(value as Category[]);
      setLoadError('');
    }).catch(error => { if (active) setLoadError(errorMessage(error)); });
    return () => { active = false; };
  }, [revision, request]);

  async function change(category: Category | null, method: 'POST' | 'PATCH' | 'DELETE') {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try {
      await request(category ? `/categories/${category.id}` : '/categories', method,
        method === 'DELETE' ? undefined : { name: name.trim() });
      setName('');
      setEditing(null);
      setRevision(value => value + 1);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) setMessage('Категория с таким названием уже есть.');
      else if (method === 'POST' && uncertainCreate(error)) {
        setMessage('Создание не подтверждено. Проверьте список категорий перед повторной отправкой.');
        setRevision(value => value + 1);
      } else {
        setMessage(errorMessage(error, 'Введите название категории длиной до 50 символов.'));
        if (error instanceof ApiError && error.status === 404) setRevision(value => value + 1);
      }
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  function remove(category: Category) {
    Alert.alert(t('Удалить категорию?'), t('Материалы останутся в библиотеке без категории.'), [
      { text: t('Отмена'), style: 'cancel' },
      { text: t('Удалить'), style: 'destructive', onPress: () => void change(category, 'DELETE') },
    ]);
  }

  return <Page title={t('Категории')} scrollRef={scrollRef}>
    <Card>
      <Text accessibilityRole="header" style={styles.heading}>{editing ? t('Переименовать категорию') : t('Новая категория')}</Text>
      <Field label={t('Название категории')} value={name} onChangeText={setName}
        maxLength={50} autoCapitalize="sentences" editable={!busy} />
      <Action title={busy ? t('Сохранение…') : t('Сохранить категорию')} disabled={busy || !name.trim()}
        onPress={() => void change(editing, editing ? 'PATCH' : 'POST')} />
      {editing && <Action title={t('Отменить переименование')} disabled={busy} onPress={() => { setEditing(null); setName(''); setMessage(''); }} />}
      {message && <Notice>{message}</Notice>}
    </Card>
    {loadError && <>
      <Notice>{loadError}</Notice>
      <Action title={t('Обновить список категорий')} onPress={() => setRevision(value => value + 1)} />
    </>}
    {!items && !loadError && <Loading />}
    {items?.length === 0 && <Body>{t('Категорий пока нет.')}</Body>}
    {items?.map(category => <Card key={category.id}>
      <Text style={styles.heading}>{category.name}</Text>
      <Body>{t('Материалов ·')} {category.contents_count}</Body>
      <RenameAction title={t('Переименовать «{0}»', category.name)} disabled={busy} onPress={() => {
        setEditing(category); setName(category.name); setMessage('');
        scrollRef.current?.scrollTo({ y: 0, animated: true });
      }} />
      <Action variant="danger" title={t('Удалить «{0}»', category.name)} disabled={busy} onPress={() => remove(category)} />
    </Card>)}
  </Page>;
}
