import { useEffect, useState } from 'react';
import { AppState, Linking, Text } from 'react-native';
import { router } from 'expo-router';
import { clearSharedPayloads, getSharedPayloads } from 'expo-sharing';
import { Action, Body, Card, Page } from '../components/ui';
import { inspectShare, type ShareResult } from '../platform/share';

export default function ShareProbe() {
  const [result, setResult] = useState<ShareResult | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const refresh = () => {
      try {
        const payloads = getSharedPayloads();
        setResult(payloads.length ? inspectShare(payloads) : null);
        setError(false);
      } catch { setError(true); }
    };
    refresh();
    const appState = AppState.addEventListener('change', state => { if (state === 'active') refresh(); });
    const links = Linking.addEventListener('url', refresh);
    return () => { appState.remove(); links.remove(); };
  }, []);

  function discard() {
    try {
      clearSharedPayloads();
      setResult(null);
      router.replace('/');
    } catch { setError(true); }
  }

  return <Page title="Входящий материал"><Card>
    <Body>Проверка приёма через «Поделиться». Материал не сохраняется в библиотеку и не отправляется на сервер.</Body>
    {error ? <Body>Не удалось прочитать или очистить входящие данные. Повторите проверку в установленной сборке.</Body>
      : result?.ok ? <>
        <Body>{result.item.kind === 'url' ? 'Получена ссылка' : 'Получен текст'}</Body>
        <Text selectable>{result.item.value}</Text>
      </> : <Body>{result ? result.message : 'Входящих данных пока нет. Поделитесь ссылкой или текстом из другого приложения.'}</Body>}
    <Action title="Очистить и закрыть" onPress={discard} />
  </Card></Page>;
}
