import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Action, Body, styles } from '../components/ui';
import { colors } from '../theme';
import Ionicons from '@expo/vector-icons/Ionicons';
import type { Group } from './organization';
import { useTranslation } from '../i18n';

export function GroupSelection({ label, items, selected, onChange, disabled }: {
  label: string; items: Group[]; selected: number[]; onChange: (value: number[]) => void; disabled: boolean;
}) {
  const t = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [limited, setLimited] = useState(false);
  const names = items.filter(item => selected.includes(item.id)).map(item => item.name);
  return <View style={{ gap: 8 }}>
    <Action variant="outline" title={`${label} · ${names.length ? names.join(', ') : t('Не выбраны')}`} disabled={disabled} onPress={() => setExpanded(!expanded)} />
    {expanded && <>
      {items.length === 0 && <Body>{t('Список пуст. Создайте тег или коллекцию в управлении библиотекой.')}</Body>}
      {items.map(item => <Pressable key={item.id} accessibilityRole="checkbox" accessibilityLabel={item.name} disabled={disabled}
        accessibilityState={{ checked: selected.includes(item.id), disabled }}
        onPress={() => {
          const checked = selected.includes(item.id);
          if (!checked && selected.length >= 20) { setLimited(true); return; }
          setLimited(false); onChange(checked ? selected.filter(id => id !== item.id) : [...selected, item.id]);
        }} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, minHeight: 48 }}>
        <Ionicons name={selected.includes(item.id) ? 'checkbox' : 'square-outline'} size={20} color={colors.primary} />
        <Text style={styles.body}>{item.name}</Text>
      </Pressable>)}
    </>}
    {limited && <Body>{t('Можно выбрать не более 20.')}</Body>}
  </View>;
}
