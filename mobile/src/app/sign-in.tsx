import { useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { openURL } from 'expo-linking';
import { Action, Body, Field, Page, styles } from '../components/ui';
import { useAuth } from '../auth/context';
import { API_ORIGIN, PUBLIC_LINKS, STAGING_GATE } from '../auth/config';
import { colors } from '../theme';

export default function SignIn() {
  const { controller, state } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { terms, privacy } = PUBLIC_LINKS;
  if (state.phase === 'signedIn') return <Redirect href="/account" />;
  async function submit() {
    setError(null);
    try {
      if (mode === 'register' && name.trim()) await controller.signIn(mode, email.trim(), password, consent, name.trim());
      else await controller.signIn(mode, email.trim(), password, consent);
      setPassword(''); router.replace('/account');
    } catch (error) {
      setPassword(''); setError(error instanceof Error ? error.message : 'Не удалось войти.');
    }
  }
  return <Page auth title={mode === 'login' ? 'С возвращением' : 'Создать аккаунт'}
    subtitle={mode === 'login' ? 'Войдите или создайте аккаунт, чтобы продолжить.' : 'Сохраняйте то, что важно для вас.'}>
    {mode === 'register' && <Field label="Имя" placeholder="Как к вам обращаться" value={name} onChangeText={setName}
      autoComplete="name" autoCapitalize="words" editable={!state.busy} maxLength={80} />}
    <Field label="Электронная почта" placeholder="you@example.com" value={email} onChangeText={setEmail} keyboardType="email-address" autoComplete="email" textContentType="emailAddress" editable={!state.busy} maxLength={320} />
    <Field label="Пароль" placeholder="Введите пароль" value={password} onChangeText={setPassword} secureTextEntry autoComplete={mode === 'login' ? 'current-password' : 'new-password'} textContentType={mode === 'login' ? 'password' : 'newPassword'} editable={!state.busy} maxLength={128} />
    {mode === 'register' && <View style={{ gap: 12 }}>
      <Body>Пароль: от 10 до 128 символов. Пробелы тоже считаются частью пароля.</Body>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Text style={[styles.body, { flex: 1 }]}>Я даю согласие на обработку персональных данных.</Text>
        <Switch accessibilityLabel="Согласие на обработку персональных данных" value={consent} onValueChange={setConsent} disabled={state.busy}
          trackColor={{ true: colors.primary }} />
      </View>
    </View>}
    {error && <Text accessibilityLiveRegion="polite" style={[styles.body, styles.danger]}>{error}</Text>}
    <Action title={state.busy ? 'Подождите…' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'} disabled={!API_ORIGIN || state.busy || !email.trim() || !password || (mode === 'register' && (!consent || password.length < 10))} onPress={() => void submit()} />
    <Action variant="text" title={mode === 'login' ? 'Создать аккаунт' : 'Уже есть аккаунт? Войти'} disabled={state.busy} onPress={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null); setPassword(''); }} />
    {mode === 'login' && <Action variant="text" title="Забыли пароль?" disabled={state.busy} onPress={() => { setPassword(''); router.push('/reset-password'); }} />}
    {STAGING_GATE && <>
      <Body>Закрытое тестирование. Используйте вымышленные данные. Версия согласия — draft-1.</Body>
      <Action variant="outline" title="Доступ к тестовому стенду" disabled={state.busy} onPress={() => router.push('/staging-access')} />
    </>}
    {!API_ORIGIN && <Body>Подключение к серверу ещё не настроено в этой сборке.</Body>}
    {(terms || privacy) && <View style={{ flexDirection: 'row', justifyContent: 'center', flexWrap: 'wrap' }}>
      {terms && <Action variant="text" title="Условия использования"
        onPress={() => void openURL(terms).catch(() => setError('Не удалось открыть условия.'))} />}
      {privacy && <Action variant="text" title="Политика конфиденциальности"
        onPress={() => void openURL(privacy).catch(() => setError('Не удалось открыть политику.'))} />}
    </View>}
  </Page>;
}
