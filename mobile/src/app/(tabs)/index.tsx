import { useTranslation } from '../../i18n';
import { Today } from '../../learning/Today';
import { LibraryAccess } from '../../library/ui';

export default function TodayScreen() {
  const t = useTranslation();
  return <LibraryAccess title={t('Сегодня')}>{(request, owner) => <Today request={request} owner={owner} />}</LibraryAccess>;
}
