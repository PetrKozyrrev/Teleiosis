import { useState } from 'react';
import { Text } from 'react-native';
import { router } from 'expo-router';
import { Action, Body, Card, Page } from '../components/ui';
import { storageProbe, type ProbeOperation } from '../platform/storageProbe';
import { useTranslation } from '../i18n';

export default function DeviceProbe() {
  const t = useTranslation();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('Проверка ещё не запускалась.');
  async function run(operation: ProbeOperation) {
    if (busy) return;
    setBusy(true);
    try { setStatus(await storageProbe(operation)); }
    catch { setStatus('Проверка не выполнена. Повторите на разблокированном устройстве в установленной сборке.'); }
    finally { setBusy(false); }
  }
  return <Page title={t('Проверка устройства')}><Card>
    <Body>{t('Защищённое хранилище')}</Body>
    <Body>{t('Используется отдельная проверочная запись без паролей и личных данных.')}</Body>
    <Action title={t('Записать и проверить')} disabled={busy} onPress={() => void run('write')} />
    <Action title={t('Прочитать после перезапуска')} disabled={busy} onPress={() => void run('read')} />
    <Action title={t('Удалить проверочную запись')} disabled={busy} onPress={() => void run('delete')} />
    <Text accessibilityLiveRegion="polite">{busy ? t('Проверка…') : t(status)}</Text>
  </Card><Card>
    <Body>{t('В браузере или другом приложении выберите ссылку или текст → «Поделиться» → «Телеосис · тест».')}</Body>
    <Action title={t('Открыть входящий материал')} onPress={() => router.push('/share-probe')} />
  </Card></Page>;
}
