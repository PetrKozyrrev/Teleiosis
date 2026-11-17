import { router } from 'expo-router';
import { Action, Body, Card, Page } from '../../components/ui';

export default function Settings() {
  return <Page title="Настройки"><Card>
    <Body>Тестовая сборка · версия 0.2.0</Body>
    <Action title="Аккаунт" onPress={() => router.push('/account')} />
    <Body>Можно проверить защищённое хранилище и приём материалов через «Поделиться».</Body>
    <Action title="Проверить устройство" onPress={() => router.push('/probe')} />
    <Action title="Посмотреть входящий материал" onPress={() => router.push('/share-probe')} />
    <Action title="Лицензии шрифтов" onPress={() => router.push('/licenses')} />
  </Card></Page>;
}
