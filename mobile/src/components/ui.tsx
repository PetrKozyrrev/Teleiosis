import type { ComponentRef, PropsWithChildren, Ref } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps } from 'react-native';
import { colors, fonts } from '../theme';

export function Page({ title, children, scrollRef }: PropsWithChildren<{ title: string; scrollRef?: Ref<ComponentRef<typeof ScrollView>> }>) {
  return <KeyboardAvoidingView style={styles.page} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={80}>
    <ScrollView ref={scrollRef} keyboardShouldPersistTaps="handled" style={styles.page} contentContainerStyle={styles.content}>
    <Text style={styles.eyebrow}>ТЕЛЕОСИС</Text>
    <Text accessibilityRole="header" style={styles.title}>{title}</Text>
    {children}
  </ScrollView></KeyboardAvoidingView>;
}

export function Field({ label, style, ...props }: TextInputProps & { label: string }) {
  return <View style={{ gap: 8 }}>
    <Text style={styles.body}>{label}</Text>
    <TextInput accessibilityLabel={label} autoCapitalize="none" autoCorrect={false}
      style={[{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 14, minHeight: 48, color: colors.text, backgroundColor: colors.surface, fontFamily: fonts.body, fontSize: 16 }, style]} {...props} />
  </View>;
}

export function Card({ children }: PropsWithChildren) {
  return <View style={styles.card}>{children}</View>;
}

export function Body({ children }: PropsWithChildren) {
  return <Text style={styles.body}>{children}</Text>;
}

export function Action({ title, onPress, disabled = false }: {
  title: string; onPress: () => void; disabled?: boolean;
}) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }}
    disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.button, (pressed || disabled) && styles.dimmed]}>
    <Text style={styles.buttonText}>{title}</Text>
  </Pressable>;
}

export const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  content: { padding: 24, gap: 20, paddingBottom: 40, width: '100%', maxWidth: 680, alignSelf: 'center' },
  eyebrow: { color: colors.primary, fontSize: 12, fontFamily: fonts.bold, letterSpacing: 2 },
  title: { color: colors.text, fontSize: 32, fontFamily: fonts.heading },
  heading: { color: colors.text, fontSize: 21, fontFamily: fonts.heading },
  body: { color: colors.muted, fontSize: 16, lineHeight: 25, fontFamily: fonts.body },
  card: { backgroundColor: colors.surface, borderRadius: 16, padding: 24, gap: 16 },
  button: { backgroundColor: colors.primary, borderRadius: 12, minHeight: 48, padding: 14, justifyContent: 'center' },
  buttonText: { textAlign: 'center', color: colors.surface, fontSize: 16, fontFamily: fonts.medium },
  dimmed: { opacity: 0.55 },
});
