import { useEffect, useState } from 'react';
import { AppState, Linking, Platform, Text } from 'react-native';
import { router } from 'expo-router';
import { clearSharedPayloads, getSharedPayloads } from 'expo-sharing';
import { Action, Body, Card, Page } from '../components/ui';
import { inspectShare, type ShareResult } from '../platform/share';
import { importDraft } from '../offline/store';

export default function IncomingShare() {
  const [result, setResult] = useState<ShareResult | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (Platform.OS !== 'android') return;
    let active = true;
    let processing = false;
    async function refresh() {
      if (processing) return;
      processing = true;
      try {
        while (active) {
          const payloads = getSharedPayloads();
          if (!payloads.length) break;
          const inspected = inspectShare(payloads);
          setResult(inspected);
          setSaved(false);
          setError(false);
          if (!inspected.ok) break;
          const { item } = inspected;
          await importDraft(item.kind === 'url' ? { url: item.value } : { note: item.value });
          if (!active) break;
          if (JSON.stringify(getSharedPayloads()) !== JSON.stringify(payloads)) continue;
          clearSharedPayloads();
          setSaved(true);
          break;
        }
      } catch { if (active) setError(true); }
      finally { processing = false; }
    }
    void refresh();
    const appState = AppState.addEventListener('change', state => { if (state === 'active') void refresh(); });
    const links = Linking.addEventListener('url', () => { void refresh(); });
    return () => { active = false; appState.remove(); links.remove(); };
  }, [revision]);

  function dismissUnsupported() {
    try { clearSharedPayloads(); router.replace('/queue'); }
    catch { setError(true); }
  }

  return <Page title="Входящий материал"><Card>
    {error ? <>
      <Body>Не удалось обработать входящие данные. Повторите локальное сохранение.</Body>
      <Action title="Повторить" onPress={() => setRevision(value => value + 1)} />
    </> : result?.ok ? <>
      {saved && <Body>Черновик сохранён на устройстве. Выберите его во входящих и подтвердите добавление в аккаунт.</Body>}
      <Text selectable>{result.item.value}</Text>
    </> : <Body>{result ? result.message : 'Откройте входящие или поделитесь одной ссылкой или текстом.'}</Body>}
    <Action title="Открыть входящие" onPress={() => router.replace('/queue')} />
    {result && !result.ok && <Action title="Закрыть и очистить входящий материал" onPress={dismissUnsupported} />}
  </Card></Page>;
}
