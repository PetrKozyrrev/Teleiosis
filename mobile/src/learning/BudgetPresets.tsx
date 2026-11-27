import { StyleSheet, View } from 'react-native';
import { Action } from '../components/ui';
import { useTranslation } from '../i18n';
import type { LearningBudget } from './events';

const budgets = [5, 15, 30, 60] as const;

export function parseBudget(value?: string | string[]): LearningBudget | null {
  return budgets.find(budget => String(budget) === value) ?? null;
}

export function BudgetPresets({ selected, onSelect }: {
  selected?: LearningBudget | null;
  onSelect: (value: LearningBudget) => void;
}) {
  const t = useTranslation();
  return <View style={styles.row}>
    {budgets.map(value =>
      <Action key={value} title={t('{0} мин', value)} onPress={() => onSelect(value)}
        selected={selected === undefined ? undefined : selected === value}
        variant={selected === value ? 'primary' : 'outline'} style={styles.preset} />,
    )}
  </View>;
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  preset: { flexGrow: 1, flexBasis: '40%' },
});
