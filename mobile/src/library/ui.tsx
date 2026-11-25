import { router } from 'expo-router';
import { useMemo, useState, type PropsWithChildren } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { useAuth } from '../auth/context';
import { ApiError } from '../auth/api';
import { API_ORIGIN } from '../auth/config';
import { Action, Body, Card, Page, styles } from '../components/ui';
import { colors } from '../theme';
import type { Request } from './model';
import { ownerKey } from '../offline/store';
import { translate, useTranslation } from '../i18n';

export function Notice({ children }: PropsWithChildren) {
  const t = useTranslation();
  return <Text accessibilityLiveRegion="polite" style={styles.body}>{typeof children === 'string' ? t(children) : children}</Text>;
}

export function Loading() {
  const t = useTranslation();
  return <View style={{ gap: 8, alignItems: 'center' }}>
    <ActivityIndicator color={colors.primary} />
    <Notice>{t('Загрузка…')}</Notice>
  </View>;
}

export function RenameAction({ title, onPress, disabled }: {
  title: string; onPress: () => void; disabled: boolean;
}) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.button, { backgroundColor: colors.coolTint }, pressed && styles.dimmed]}>
    <Text style={[styles.buttonText, { color: colors.text }, disabled && styles.disabledText]}>{title}</Text>
  </Pressable>;
}

export function Choice<T extends string | number | null>({ label, value, options, onChange, disabled, hideLabel }: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
  hideLabel?: boolean;
}) {
  const t = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const selectedLabel = options.find(option => option.value === value)?.label ?? t('Недоступно');
  return <View style={{ gap: 6 }}>
    <Pressable accessibilityRole="button" accessibilityState={{ disabled, expanded }} disabled={disabled}
      accessibilityLabel={hideLabel ? `${label} · ${selectedLabel}` : undefined}
      onPress={() => setExpanded(!expanded)}
      style={{ minHeight: 48, justifyContent: 'center', padding: 10, borderWidth: 1, borderColor: colors.border, borderRadius: 12 }}>
      <Text style={styles.body}>{hideLabel ? selectedLabel : `${label} · ${selectedLabel}`}</Text>
    </Pressable>
    {expanded && !disabled && options.map(option => <Pressable key={String(option.value)} accessibilityRole="radio"
      accessibilityState={{ checked: option.value === value }}
      onPress={() => { onChange(option.value); setExpanded(false); }}
      style={{ minHeight: 48, justifyContent: 'center', paddingHorizontal: 12, backgroundColor: colors.background, borderRadius: 8 }}>
      <Text style={styles.body}>{option.label}</Text>
    </Pressable>)}
  </View>;
}

export function optionsOf<T extends string>(labels: Record<T, string>) {
  return (Object.keys(labels) as T[]).map(value => ({ value, label: translate(labels[value]) }));
}

export function LibraryAccess({ children, title, brand }: {
  children: (request: Request, owner: string | null) => React.ReactNode; title?: string; brand?: boolean;
}) {
  const t = useTranslation();
  const { controller, state } = useAuth();
  const session = state.session;
  const phase = state.phase;
  const id = state.session?.user.id ?? (state.phase === 'offline' ? state.offlineOwner : null);
  const request = useMemo<Request>(() => {
    const isCurrent = controller.captureSession();
    return (...args) => {
      if (!id || !isCurrent()) return Promise.reject(new ApiError(401));
      if (phase === 'offline' && session === null) return Promise.reject(new ApiError(0));
      return controller.library(...args);
    };
  }, [controller, id, phase, session]);
  if (id) return <View key={id} style={{ flex: 1 }}>{children(request, API_ORIGIN ? ownerKey(API_ORIGIN, id) : null)}</View>;
  return <Page title={title ?? t('Библиотека')} brand={brand}><Card>
    {state.phase === 'loading' ? <Loading /> : <>
      {state.message && <Notice>{state.message}</Notice>}
      {state.phase === 'signedOut' ? <>
        <Body>{t('Войдите, чтобы работать с библиотекой.')}</Body>
        <Action title={t('Войти')} onPress={() => router.push('/sign-in')} />
      </> : <>
        <Action title={t('Повторить проверку сессии')} disabled={state.busy} onPress={() => void controller.initialize().catch(() => {})} />
        <Action title={t('Аккаунт')} onPress={() => router.push('/account')} />
      </>}
      <Action title={t('Входящие материалы')} onPress={() => router.push('/share-probe')} />
    </>}
  </Card></Page>;
}
