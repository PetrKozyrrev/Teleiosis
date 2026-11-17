import { Text } from 'react-native';
import { router } from 'expo-router';
import { Action, Body, Card, Page, styles } from '../../components/ui';

export default function Library() {
  return <Page title="Место для ваших знаний">
    <Card>
      <Text style={styles.heading}>Сохраняйте то, к чему хочется вернуться</Text>
      <Body>Здесь появятся ваши ссылки, заметки и материалы для изучения.</Body>
      <Body>Войдите в аккаунт, чтобы проверить доступ с телефона. Подключение библиотеки — следующий этап.</Body>
      <Action title="Аккаунт" onPress={() => router.push('/account')} />
      <Action title="Проверить устройство" onPress={() => router.push('/probe')} />
    </Card>
  </Page>;
}
