import { Text } from 'react-native';
import { Page, styles } from '../components/ui';
import { fontLicenses } from '../fontLicenses';

export default function Licenses() {
  return <Page title="Лицензии шрифтов"><Text selectable style={styles.body}>{fontLicenses}</Text></Page>;
}
