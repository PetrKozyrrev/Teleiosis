import { Text } from 'react-native';
import { Page, styles } from '../components/ui';
import { fontLicenses } from '../fontLicenses';
import { useTranslation } from '../i18n';

export default function Licenses() {
  const t = useTranslation();
  return <Page title={t('Лицензии шрифтов')}><Text selectable style={styles.body}>{fontLicenses}</Text></Page>;
}
