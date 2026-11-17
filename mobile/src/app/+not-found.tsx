import { router } from 'expo-router';
import { Action, Body, Page } from '../components/ui';

export default function NotFound() {
  return <Page title="Страница не найдена">
    <Body>Этот адрес пока не поддерживается приложением.</Body>
    <Action title="В библиотеку" onPress={() => router.replace('/')} />
  </Page>;
}
