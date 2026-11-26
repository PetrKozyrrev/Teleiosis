import { useTranslation } from '../i18n';
import { TimeBudget } from '../learning/TimeBudget';
import { LibraryAccess } from '../library/ui';

export default function TimeBudgetRoute() {
  const t = useTranslation();
  return <LibraryAccess title={t('Сколько у вас времени?')}>{(request, owner) =>
    <TimeBudget request={request} owner={owner} />
  }</LibraryAccess>;
}
