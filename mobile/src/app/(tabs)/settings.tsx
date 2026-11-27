import Ionicons from '@expo/vector-icons/Ionicons';
import Constants from 'expo-constants';
import { openURL } from 'expo-linking';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState, type ComponentProps, type ReactNode } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { SignOut } from '../../account/SignOut';
import { ApiError, type Profile, type User } from '../../auth/api';
import { PUBLIC_LINKS, STAGING_GATE } from '../../auth/config';
import { useAuth } from '../../auth/context';
import { Action, Body, BrandToggle, Card, Field, Page, styles } from '../../components/ui';
import { errorMessage, type Request } from '../../library/model';
import { LibraryAccess, Loading, Notice } from '../../library/ui';
import { colors } from '../../theme';
import { languageNames, saveLanguage, useLanguage, useTranslation, type Language } from '../../i18n';

export default function ProfileTab() {
  const t = useTranslation();
  return <LibraryAccess title={t('Профиль')} brand>{request => <ProfileView request={request} />}</LibraryAccess>;
}

function ProfileView({ request }: { request: Request }) {
  const t = useTranslation();
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
  const display = profile?.display_name ?? email ?? t('Профиль недоступен офлайн');
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
  return <Page title={t('Профиль')} subtitle={t('Настройте приложение для своего чтения.')} brand>
    <Card><View style={screenStyles.profile}>
      <View style={screenStyles.avatar}><Ionicons name="person" color={colors.primary} size={26} /></View>
      <View style={screenStyles.details}>
        <Text style={styles.label}>{display}</Text>
        {profile?.display_name && email && <Body>{email}</Body>}
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel={t('Редактировать профиль')} accessibilityState={{ disabled: cannotEdit }}
        disabled={cannotEdit} style={screenStyles.edit} onPress={() => { setEditing('name'); setName(profile?.display_name ?? ''); }}>
        <Ionicons name="pencil" color={colors.primary} size={20} />
      </Pressable>
    </View></Card>
    <Text style={screenStyles.section}>{t('Настройки чтения')}</Text>
    <Card>
      <ProfileRow icon="disc-outline" title={t('Недельная норма')} value={profile?.weekly_reading_goal?.toString()}
        disabled={cannotEdit} onPress={() => { setEditing('goal'); setGoal(String(profile?.weekly_reading_goal ?? '')); }} />
      <Body>{t('Число изученных материалов за неделю. Бюджет времени задаётся в недельном плане.')}</Body>
      <View style={screenStyles.divider} />
      <ProfileRow icon="notifications-outline" title={t('Напоминания о чтении')} trailing={<BrandToggle label={t('Напоминания о чтении')}
        checked={Boolean(user?.reminders_enabled)} disabled={!user || busy || offline} onChange={changeReminders} />} />
      <View style={screenStyles.divider} />
      <ProfileRow icon="time-outline" title={t('Время и часовой пояс')} onPress={() => router.push('/reading-schedule')} />
      <View style={screenStyles.divider} />
      <AppLanguage />
    </Card>
    {editing && <Modal transparent animationType="fade" onRequestClose={() => { if (!busy) setEditing(undefined); }}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={screenStyles.modal} accessibilityViewIsModal>
        <View style={screenStyles.dialog}><Card>
          <Text accessibilityRole="header" style={styles.heading}>{editing === 'name' ? t('Редактировать профиль') : t('Недельная норма')}</Text>
          {editing === 'name'
            ? <Field label={t('Имя')} value={name} onChangeText={setName} editable={!busy} maxLength={80} autoCapitalize="words" />
            : <Field label={t('Материалов в неделю')} value={goal} onChangeText={setGoal} keyboardType="number-pad" maxLength={3} editable={!busy} />}
          {editing === 'goal' && <Body>{t('Укажите число от 1 до 100.')}</Body>}
          {message && <Notice>{message}</Notice>}
          <Action title={t('Сохранить')} onPress={saveProfile} disabled={(editing === 'goal' && !validGoal) || busy || offline} />
          <Action variant="outline" title={t('Отмена')} onPress={() => setEditing(undefined)} disabled={busy} />
        </Card></View>
      </KeyboardAvoidingView>
    </Modal>}
    {!profile && !message && <Loading />}
    {message && !editing && <><Notice>{message}</Notice><Action variant="text" title={t('Обновить профиль')} disabled={busy} onPress={() => setRevision(value => value + 1)} /></>}
    <Text style={screenStyles.section}>{t('Аккаунт и поддержка')}</Text>
    <Card>
      <ProfileRow icon="shield-checkmark-outline" title={t('Аккаунт и безопасность')} onPress={() => router.push('/account')} />
      <View style={screenStyles.divider} />
      <ProfileRow icon="settings-outline" title={t('Пароль и данные')} onPress={() => router.push('/preferences')} />
      {support && <>
        <View style={screenStyles.divider} />
        <ProfileRow icon="help-circle-outline" title={t('Помощь и обратная связь')}
          onPress={() => void openURL(support).catch(() => setMessage('Не удалось открыть страницу поддержки.'))} />
      </>}
      <View style={screenStyles.divider} />
      <ProfileRow icon="information-circle-outline" title={t('Лицензии шрифтов')} onPress={() => router.push('/licenses')} />
      {STAGING_GATE && <ProfileRow icon="construct-outline" title={t('Проверить устройство')} onPress={() => router.push('/probe')} />}
    </Card>
    <SignOut />
    <Text style={[styles.body, screenStyles.version]}>Teleiosis · {Constants.expoConfig?.version}</Text>
  </Page>;
}

const appLanguages: Language[] = ['ru', 'en'];

function AppLanguage() {
  const language = useLanguage();
  const t = useTranslation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const saving = useRef(false);

  async function select(value: Language) {
    if (saving.current) return;
    if (value === language) { setOpen(false); return; }
    saving.current = true;
    setBusy(true);
    setFailed(false);
    try {
      await saveLanguage(value);
      setOpen(false);
    } catch { setFailed(true); }
    finally { saving.current = false; setBusy(false); }
  }

  const title = t('Язык приложения');
  return <>
    <ProfileRow icon="language-outline" title={title} value={languageNames[language]} expanded={open}
      disabled={busy} onPress={() => { setFailed(false); setOpen(!open); }} />
    {open && <>
      {appLanguages.map(value => <Pressable key={value} accessibilityRole="radio" accessibilityLanguage={value} accessibilityLabel={languageNames[value]}
        accessibilityState={{ checked: value === language, disabled: busy }} disabled={busy}
        style={screenStyles.languageOption} onPress={() => void select(value)}>
        <Ionicons name={value === language ? 'radio-button-on' : 'radio-button-off'} size={20} color={colors.primary} />
        <Text style={styles.body}>{languageNames[value]}</Text>
      </Pressable>)}
      {failed && <Notice>{t('Не удалось сохранить язык приложения. Повторите попытку.')}</Notice>}
    </>}
  </>;
}

function ProfileRow({ icon, title, value, onPress, disabled, trailing, expanded }: {
  icon: ComponentProps<typeof Ionicons>['name']; title: string; value?: string; onPress?: () => void;
  disabled?: boolean; trailing?: ReactNode; expanded?: boolean;
}) {
  const content = <>
    <Ionicons name={icon} size={20} color={colors.muted} />
    <Text style={[styles.label, screenStyles.details]}>{title}</Text>
    {value && <Body>{value}</Body>}
    {trailing}
    {onPress && <Ionicons name={expanded ? 'chevron-up' : 'chevron-forward'} size={17} color={colors.muted} />}
  </>;
  return onPress ? <Pressable accessibilityRole="button" accessibilityState={{ disabled, expanded }} disabled={disabled}
    onPress={onPress} style={screenStyles.row}>{content}</Pressable> : <View style={screenStyles.row}>{content}</View>;
}

const screenStyles = StyleSheet.create({
  profile: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  avatar: { height: 48, width: 48, borderRadius: 24, backgroundColor: colors.tint, alignItems: 'center', justifyContent: 'center' },
  details: { flex: 1 },
  edit: { height: 44, width: 44, borderRadius: 12, backgroundColor: colors.tint, alignItems: 'center', justifyContent: 'center' },
  section: { ...styles.label, color: colors.muted, fontSize: 12, textTransform: 'uppercase' },
  row: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 10 },
  languageOption: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 10, paddingLeft: 12 },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  version: { textAlign: 'center' },
  modal: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#21212455', padding: 20 },
  dialog: { width: '100%', maxWidth: 460 },
});
