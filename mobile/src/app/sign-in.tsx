import { useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { Action, Body, Card, Field, Page } from '../components/ui';
import { useAuth } from '../auth/context';
import { API_ORIGIN, STAGING_GATE } from '../auth/config';

export default function SignIn() {
  const { controller, state } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (state.phase === 'signedIn') return <Redirect href="/account" />;
  async function submit() {
    setError(null);
    try {
      await controller.signIn(mode, email.trim(), password, consent);
      setPassword(''); router.replace('/account');
    } catch (error) {
      setPassword(''); setError(error instanceof Error ? error.message : 'Не удалось войти.');
    }
  }
  return <Page title={mode === 'login' ? 'С возвращением' : 'Создать аккаунт'}><Card>
    {STAGING_GATE && <Body>Закрытое тестирование: используйте вымышленные данные. Текст согласия пока имеет тестовую версию draft-1.</Body>}
    {!API_ORIGIN && <Body>Подключение к серверу ещё не настроено в этой сборке.</Body>}
    <Field label="Электронная почта" value={email} onChangeText={setEmail} keyboardType="email-address" autoComplete="email" textContentType="emailAddress" editable={!state.busy} maxLength={320} />
    <Field label="Пароль" value={password} onChangeText={setPassword} secureTextEntry autoComplete={mode === 'login' ? 'current-password' : 'new-password'} textContentType={mode === 'login' ? 'password' : 'newPassword'} editable={!state.busy} maxLength={128} />
    {mode === 'register' && <View style={{ gap: 12 }}>
      <Body>Пароль: от 10 до 128 символов. Пробелы тоже считаются частью пароля.</Body>
      <Body>Я даю согласие на обработку персональных данных.</Body>
      <Switch accessibilityLabel="Согласие на обработку персональных данных" value={consent} onValueChange={setConsent} disabled={state.busy} />
    </View>}
    {error && <Text accessibilityLiveRegion="polite">{error}</Text>}
    <Action title={state.busy ? 'Подождите…' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'} disabled={!API_ORIGIN || state.busy || !email.trim() || !password || (mode === 'register' && (!consent || password.length < 10))} onPress={() => void submit()} />
    <Action title={mode === 'login' ? 'Создать аккаунт' : 'Уже есть аккаунт'} disabled={state.busy} onPress={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null); setPassword(''); }} />
    <Action title="Забыли пароль?" disabled={state.busy} onPress={() => { setPassword(''); router.push('/reset-password'); }} />
    {STAGING_GATE && <Action title="Доступ к тестовому стенду" disabled={state.busy} onPress={() => router.push('/staging-access')} />}
  </Card></Page>;
}
