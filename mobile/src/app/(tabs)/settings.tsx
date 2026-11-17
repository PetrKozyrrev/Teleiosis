import { router } from 'expo-router';
import { Action, Body, Card, Page } from '../../components/ui';

export default function Settings() {
  return <Page title="Настройки"><Card>
    <Body>Тестовый каркас · версия 0.1.0</Body>
    <Body>Можно проверить защищённое хранилище и приём материалов через «Поделиться».</Body>
    <Action title="Проверить устройство" onPress={() => router.push('/probe')} />
    <Action title="Посмотреть входящий материал" onPress={() => router.push('/share-probe')} />
    <Action title="Лицензии шрифтов" onPress={() => router.push('/licenses')} />
  </Card></Page>;
}
