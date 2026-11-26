import { useLocalSearchParams } from 'expo-router';
import { Page } from '../../components/ui';
import { useTranslation } from '../../i18n';
import { GoalsList } from '../../learning/goals';
import { parseId } from '../../library/model';
import { LibraryAccess, Notice } from '../../library/ui';

export default function MaterialGoalsRoute() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const value = parseId(id);
  const t = useTranslation();
  return <LibraryAccess title={t('Добавить к цели')}>{request => value
    ? <GoalsList key={value} request={request} contentId={value} />
    : <Page title={t('Добавить к цели')}><Notice>{t('Недоступно')}</Notice></Page>}</LibraryAccess>;
}
