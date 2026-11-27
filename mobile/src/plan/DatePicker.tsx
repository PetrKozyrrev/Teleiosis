import { useState } from 'react';
import { Modal, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Action, Page, styles } from '../components/ui';
import { useLocale, useTranslation } from '../i18n';
import { colors } from '../theme';
import { formatPlanDay, mondayOf, shiftDay, validDay } from './model';

export function DatePicker({ value, onChange, disabled }: {
  value: string; onChange: (day: string) => void; disabled: boolean;
}) {
  const t = useTranslation();
  const locale = useLocale();
  const [week, setWeek] = useState<string>();
  const close = () => setWeek(undefined);
  const label = t('Выбрать дату');
  const dateLabel = formatPlanDay(value, locale, { dateStyle: 'long' });
  return <>
    <Action variant="outline" title={dateLabel} accessibilityLabel={t('Выбрать дату: {0}', dateLabel)}
      disabled={disabled} onPress={() => setWeek(mondayOf(value))} />
    <Modal visible={week !== undefined} onRequestClose={close} animationType="slide">
      {week && <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }} accessibilityViewIsModal>
        <Page title={label}>
          <WeekNav week={week} onChange={setWeek} />
          {Array.from({ length: 7 }, (_, index) => shiftDay(week, index)).filter(validDay).map(day =>
            <Action key={day} variant={day === value ? 'primary' : 'outline'}
              title={formatPlanDay(day, locale, { dateStyle: 'full' })} selected={day === value}
              onPress={() => { onChange(day); close(); }} />,
          )}
          <Action variant="text" title={t('Отмена')} onPress={close} />
        </Page>
      </SafeAreaView>}
    </Modal>
  </>;
}

export function WeekNav({ week, onChange, disabled }: {
  week: string; onChange: (week: string) => void; disabled?: boolean;
}) {
  const t = useTranslation();
  const locale = useLocale();
  const start = formatPlanDay(week, locale, { day: 'numeric', month: 'short', year: 'numeric' });
  const end = formatPlanDay(shiftDay(week, 6), locale, { day: 'numeric', month: 'short', year: 'numeric' });
  const previous = shiftDay(week, -7);
  const next = shiftDay(week, 7);
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
    <Action variant="outline" title="‹" accessibilityLabel={t('Предыдущая неделя')}
      disabled={disabled || !validDay(shiftDay(previous, 6))} onPress={() => onChange(previous)} style={{ minWidth: 48 }} />
    <Text style={[styles.label, { flex: 1, minWidth: 100, textAlign: 'center' }]}>{start} — {end}</Text>
    <Action variant="outline" title="›" accessibilityLabel={t('Следующая неделя')}
      disabled={disabled || !validDay(next)} onPress={() => onChange(next)} style={{ minWidth: 48 }} />
  </View>;
}
