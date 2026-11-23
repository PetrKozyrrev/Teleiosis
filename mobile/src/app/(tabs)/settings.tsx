import Ionicons from '@expo/vector-icons/Ionicons';
import Constants from 'expo-constants';
import { openURL } from 'expo-linking';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState, type ComponentProps, type ReactNode } from 'react';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { SignOut } from '../../account/SignOut';
import { ApiError, type Profile, type User } from '../../auth/api';
import { PUBLIC_LINKS, STAGING_GATE } from '../../auth/config';
import { useAuth } from '../../auth/context';
import { Action, Body, Card, Field, Page, styles } from '../../components/ui';
import { errorMessage, type Request } from '../../library/model';
import { LibraryAccess, Loading, Notice } from '../../library/ui';
import { colors } from '../../theme';

export default function ProfileTab() {
  return <LibraryAccess title="Профиль" brand>{request => <ProfileView request={request} />}</LibraryAccess>;
}

function ProfileView({ request }: { request: Request }) {
  const { state, controller } = useAuth();
  const [profile, setProfile] = useState<Profile>();
  const [message, setMessage] = useState('');
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<'name' | 'goal'>();
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const writeRevision = useRef(0);
  const user = profile ?? state.session?.user;
  const email = user?.email;
  const display = profile?.display_name ?? email ?? 'Профиль недоступен офлайн';
  const offline = state.phase === 'offline';
  const support = PUBLIC_LINKS.support;

  useFocusEffect(useCallback(() => {
    void revision;
    let active = true;
    const initialRevision = writeRevision.current;
    void request('/mobile/profile', 'GET').then(data => {
      if (active && initialRevision === writeRevision.current) { setProfile(data as Profile); setMessage(''); }
    }).catch(error => {
      if (!active || initialRevision !== writeRevision.current) return;
      setMessage(error instanceof ApiError && error.status === 404 && !error.gateway
        ? 'Имя и недельную цель можно будет изменить после обновления сервера.' : errorMessage(error));
    });
    return () => { active = false; };
  }, [request, revision]));

  async function update(task: () => Promise<void>) {
    if (locked.current || offline) return;
    locked.current = true;
    writeRevision.current += 1;
    setBusy(true);
    setMessage('');
    try { await task(); }
    catch (error) { setMessage(errorMessage(error)); }
    finally { locked.current = false; setBusy(false); }
  }

  function saveProfile() {
    if (!editing) return;
    void update(async () => {
      const data = editing === 'name' ? { display_name: name.trim() || null } : { weekly_reading_goal: Number(goal) };
      setProfile(await request('/mobile/profile', 'PATCH', data) as Profile);
      setEditing(undefined);
    });
  }

  function changeReminders(enabled: boolean) {
    void update(async () => {
      const saved = await request('/me/settings', 'PATCH', { reminders_enabled: enabled }) as User;
      setProfile(current => current ? { ...current, reminders_enabled: saved.reminders_enabled } : undefined);
      if (!profile) await controller.refresh();
    });
  }

  const validGoal = /^\d{1,3}$/.test(goal) && Number(goal) >= 1 && Number(goal) <= 100;
  const cannotEdit = !profile || busy || offline;
  return <Page title="Профиль" subtitle="Настройте приложение для своего чтения." brand>
    <Card><View style={screenStyles.profile}>
      <View style={screenStyles.avatar}><Ionicons name="person" color={colors.primary} size={26} /></View>
      <View style={screenStyles.details}>
        <Text style={styles.label}>{display}</Text>
        {profile?.display_name && email && <Body>{email}</Body>}
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="Редактировать профиль" accessibilityState={{ disabled: cannotEdit }}
        disabled={cannotEdit} style={screenStyles.edit} onPress={() => { setEditing('name'); setName(profile?.display_name ?? ''); }}>
        <Ionicons name="pencil" color={colors.primary} size={20} />
      </Pressable>
    </View></Card>
    {editing === 'name' && <Card>
      <Field label="Имя" value={name} onChangeText={setName} editable={!busy} maxLength={80} autoCapitalize="words" />
      <Action title="Сохранить имя" onPress={saveProfile} disabled={busy || offline} />
      <Action variant="text" title="Отмена" onPress={() => setEditing(undefined)} disabled={busy} />
    </Card>}
    <Text style={screenStyles.section}>Настройки чтения</Text>
    <Card>
      <ProfileRow icon="disc-outline" title="Недельная цель" value={profile ? `${profile.weekly_reading_goal} в неделю` : undefined}
        disabled={cannotEdit} onPress={() => { setEditing('goal'); setGoal(String(profile?.weekly_reading_goal ?? '')); }} />
      <View style={screenStyles.divider} />
      <ProfileRow icon="notifications-outline" title="Напоминания о чтении" trailing={<Switch accessibilityLabel="Напоминания о чтении"
        value={Boolean(user?.reminders_enabled)} disabled={!user || busy || offline} onValueChange={changeReminders} trackColor={{ true: colors.primary }} />} />
      <View style={screenStyles.divider} />
      <ProfileRow icon="time-outline" title="Время и часовой пояс" onPress={() => router.push('/preferences')} />
    </Card>
    {editing === 'goal' && <Card>
      <Field label="Материалов в неделю" value={goal} onChangeText={setGoal} keyboardType="number-pad" maxLength={3} editable={!busy} />
      <Body>Укажите число от 1 до 100.</Body>
      <Action title="Сохранить цель" onPress={saveProfile} disabled={!validGoal || busy || offline} />
      <Action variant="text" title="Отмена" onPress={() => setEditing(undefined)} disabled={busy} />
    </Card>}
    {!profile && !message && <Loading />}
    {message && <><Notice>{message}</Notice><Action variant="text" title="Обновить профиль" disabled={busy} onPress={() => setRevision(value => value + 1)} /></>}
    <Text style={screenStyles.section}>Аккаунт и поддержка</Text>
    <Card>
      <ProfileRow icon="shield-checkmark-outline" title="Аккаунт и безопасность" onPress={() => router.push('/account')} />
      <View style={screenStyles.divider} />
      <ProfileRow icon="settings-outline" title="Пароль и данные" onPress={() => router.push('/preferences')} />
      {support && <>
        <View style={screenStyles.divider} />
        <ProfileRow icon="help-circle-outline" title="Помощь и обратная связь"
          onPress={() => void openURL(support).catch(() => setMessage('Не удалось открыть страницу поддержки.'))} />
      </>}
      <View style={screenStyles.divider} />
      <ProfileRow icon="information-circle-outline" title="Лицензии шрифтов" onPress={() => router.push('/licenses')} />
      {STAGING_GATE && <ProfileRow icon="construct-outline" title="Проверить устройство" onPress={() => router.push('/probe')} />}
    </Card>
    <SignOut />
    <Text style={[styles.body, screenStyles.version]}>Teleiosis · {Constants.expoConfig?.version}</Text>
  </Page>;
}

function ProfileRow({ icon, title, value, onPress, disabled, trailing }: {
  icon: ComponentProps<typeof Ionicons>['name']; title: string; value?: string; onPress?: () => void;
  disabled?: boolean; trailing?: ReactNode;
}) {
  const content = <>
    <Ionicons name={icon} size={20} color={colors.muted} />
    <Text style={[styles.label, screenStyles.details]}>{title}</Text>
    {value && <Body>{value}</Body>}
    {trailing}
    {onPress && <Ionicons name="chevron-forward" size={17} color={colors.muted} />}
  </>;
  return onPress ? <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled}
    onPress={onPress} style={screenStyles.row}>{content}</Pressable> : <View style={screenStyles.row}>{content}</View>;
}

const screenStyles = StyleSheet.create({
  profile: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  avatar: { height: 48, width: 48, borderRadius: 24, backgroundColor: colors.tint, alignItems: 'center', justifyContent: 'center' },
  details: { flex: 1 },
  edit: { height: 44, width: 44, borderRadius: 12, backgroundColor: colors.tint, alignItems: 'center', justifyContent: 'center' },
  section: { ...styles.label, color: colors.muted, fontSize: 12, textTransform: 'uppercase' },
  row: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 10 },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  version: { textAlign: 'center' },
});
