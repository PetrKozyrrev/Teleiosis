import { useLocalSearchParams } from 'expo-router';
import { useTranslation } from '../i18n';
import { parseBudget } from '../learning/BudgetPresets';
import { TimeBudget } from '../learning/TimeBudget';
import { LibraryAccess } from '../library/ui';

export default function TimeBudgetRoute() {
  const t = useTranslation();
  const { minutes } = useLocalSearchParams<{ minutes?: string | string[] }>();
  const budget = parseBudget(minutes);
  return <LibraryAccess title={t('Сколько у вас времени?')}>{(request, owner) =>
    <TimeBudget key={budget} request={request} owner={owner} initialBudget={budget} />
  }</LibraryAccess>;
}
