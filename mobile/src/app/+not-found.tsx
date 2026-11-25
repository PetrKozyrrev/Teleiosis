import { router } from 'expo-router';
import { Action, Body, Page } from '../components/ui';
import { useTranslation } from '../i18n';

export default function NotFound() {
  const t = useTranslation();
  return <Page title={t('Страница не найдена')}>
    <Body>{t('Этот адрес пока не поддерживается приложением.')}</Body>
    <Action title={t('В библиотеку')} onPress={() => router.replace('/')} />
  </Page>;
}
