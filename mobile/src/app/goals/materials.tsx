import { useLocalSearchParams } from 'expo-router';
import { Page } from '../../components/ui';
import { useTranslation } from '../../i18n';
import { GoalPicker } from '../../learning/goals';
import { parseId } from '../../library/model';
import { LibraryAccess, Notice } from '../../library/ui';

export default function GoalMaterialsRoute() {
  const { goalId } = useLocalSearchParams<{ goalId?: string }>();
  const id = parseId(goalId);
  const t = useTranslation();
  return <LibraryAccess title={t('Добавить из библиотеки')}>{request => id
    ? <GoalPicker key={id} id={id} request={request} />
    : <Page title={t('Добавить из библиотеки')}><Notice>{t('Недоступно')}</Notice></Page>}</LibraryAccess>;
}
