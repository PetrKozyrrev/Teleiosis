import { useLocalSearchParams } from 'expo-router';
import { Page } from '../../components/ui';
import { useTranslation } from '../../i18n';
import { GoalDetail } from '../../learning/goals';
import { parseId } from '../../library/model';
import { LibraryAccess, Notice } from '../../library/ui';

export default function GoalRoute() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const value = parseId(id);
  const t = useTranslation();
  return <LibraryAccess title={t('Цель')}>{(request, owner) => value
    ? <GoalDetail key={value} id={value} request={request} owner={owner} />
    : <Page title={t('Цель')}><Notice>{t('Недоступно')}</Notice></Page>}</LibraryAccess>;
}
