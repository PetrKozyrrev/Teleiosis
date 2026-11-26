import { useLocalSearchParams } from 'expo-router';
import { Page } from '../../components/ui';
import { useTranslation } from '../../i18n';
import { Completion } from '../../learning/Completion';
import { parseId } from '../../library/model';
import { LibraryAccess, Notice } from '../../library/ui';

export default function CompletionRoute() {
  const { id, taskId, mode } = useLocalSearchParams<{ id?: string; taskId?: string; mode?: string }>();
  const material = parseId(id);
  const task = parseId(taskId);
  const t = useTranslation();
  return <LibraryAccess title={t('Завершение изучения')}>{(request, owner) => material
    ? <Completion key={`${material}:${task}:${mode}`} id={material} taskId={task}
      reflectionOnly={mode === 'reflection'} request={request} owner={owner} />
    : <Page title={t('Завершение изучения')}><Notice>{t('Материал не найден.')}</Notice></Page>}</LibraryAccess>;
}
