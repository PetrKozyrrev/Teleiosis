import { GoalsList } from '../../learning/goals';
import { LibraryAccess } from '../../library/ui';
import { useTranslation } from '../../i18n';

export default function GoalsRoute() {
  const t = useTranslation();
  return <LibraryAccess title={t('Цели')}>{request => <GoalsList request={request} />}</LibraryAccess>;
}
