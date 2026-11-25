import { useEffect, useState } from 'react';
import { AppState, Linking, Platform, Text } from 'react-native';
import { router } from 'expo-router';
import { clearSharedPayloads, getSharedPayloads } from 'expo-sharing';
import { API_ORIGIN } from '../auth/config';
import { useAuth } from '../auth/context';
import { Action, Body, Card, Page } from '../components/ui';
import { PendingMaterials } from '../library/PendingMaterials';
import { inspectShare, type ShareResult } from '../platform/share';
import { importDraft, ownerKey } from '../offline/store';
import { useTranslation } from '../i18n';

export default function IncomingShare() {
  const t = useTranslation();
  const { state } = useAuth();
  const id = state.session?.user.id ?? (state.phase === 'offline' ? state.offlineOwner : null);
  const owner = API_ORIGIN && id ? ownerKey(API_ORIGIN, id) : null;
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
    try { clearSharedPayloads(); router.replace('/'); }
    catch { setError(true); }
  }

  return <Page title={t('Входящий материал')}>
    {error && <Card>
      <Body>{t('Не удалось обработать входящие данные. Повторите локальное сохранение.')}</Body>
      <Action title={t('Повторить')} onPress={() => setRevision(value => value + 1)} />
    </Card>}
    {!error && result?.ok && !saved && <Text selectable>{result.item.value}</Text>}
    {!error && result && !result.ok && <Card>
      <Body>{t(result.message)}</Body>
      <Action title={t('Закрыть и очистить входящий материал')} onPress={dismissUnsupported} />
    </Card>}
    <PendingMaterials owner={owner} inboxOnly onAssigned={() => router.replace('/')} />
    <Action variant="text" title={t('В библиотеку')} onPress={() => router.replace('/')} />
  </Page>;
}
