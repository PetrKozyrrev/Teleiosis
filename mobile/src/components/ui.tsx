import type { ComponentRef, PropsWithChildren, ReactNode, Ref } from 'react';
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps } from 'react-native';
import { colors, fonts } from '../theme';

export function Page({ title, subtitle, brand, auth, footer, children, scrollRef }: PropsWithChildren<{
  title: string; subtitle?: string; brand?: boolean; auth?: boolean; footer?: ReactNode;
  scrollRef?: Ref<ComponentRef<typeof ScrollView>>;
}>) {
  return <KeyboardAvoidingView style={[styles.page, auth && styles.auth]} behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    keyboardVerticalOffset={brand ? 0 : 48}>
    <ScrollView ref={scrollRef} keyboardShouldPersistTaps="handled" style={styles.scroll} contentContainerStyle={[styles.content, auth && styles.authContent]}>
    {brand && <View style={styles.brand} accessibilityLabel="Teleiosis" accessible>
      <Image source={require('../../design/brand/teleiosis-wordmark.png')} style={styles.wordmark} resizeMode="contain" />
    </View>}
    <View style={styles.headingGroup}>
      <Text accessibilityRole="header" style={styles.title}>{title}</Text>
      {subtitle && <Body>{subtitle}</Body>}
    </View>
    {children}
    </ScrollView>
    {footer && <View style={styles.footer}>{footer}</View>}
  </KeyboardAvoidingView>;
}

export function Field({ label, style, leading, trailing, hideLabel, ...props }: TextInputProps & {
  label: string; leading?: ReactNode; trailing?: ReactNode; hideLabel?: boolean;
}) {
  const decorated = Boolean(leading || trailing);
  return <View style={{ gap: 8 }}>
    {!hideLabel && <Text style={styles.label}>{label}</Text>}
    <View style={decorated ? [styles.input, styles.inputRow] : undefined}>
      {leading}
      <TextInput accessibilityLabel={label} autoCapitalize="none" autoCorrect={false} placeholderTextColor={colors.muted}
        style={[styles.input, decorated && styles.inlineInput, style]} {...props} />
      {trailing}
    </View>
  </View>;
}

export function Card({ children }: PropsWithChildren) {
  return <View style={styles.card}>{children}</View>;
}

export function Body({ children }: PropsWithChildren) {
  return <Text style={styles.body}>{children}</Text>;
}

export function Action({ title, onPress, disabled = false, variant = 'primary' }: {
  title: string; onPress: () => void; disabled?: boolean; variant?: 'primary' | 'outline' | 'text' | 'danger';
}) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }}
    disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.button, variant === 'outline' && styles.outline, variant === 'text' && styles.textButton,
      variant === 'danger' && styles.dangerButton, disabled && styles.disabled, pressed && styles.dimmed]}>
    <Text style={[styles.buttonText, variant === 'outline' && styles.label, variant === 'text' && styles.link,
      variant === 'danger' && styles.danger, disabled && styles.disabledText]}>{title}</Text>
  </Pressable>;
}

export const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  scroll: { flex: 1 },
  auth: { backgroundImage: 'linear-gradient(160deg, #F7F5F7, #EAF0F3 43%, #F0E7EF 95%)' },
  content: { paddingHorizontal: 20, paddingTop: 12, gap: 16, paddingBottom: 24, width: '100%', maxWidth: 640, alignSelf: 'center' },
  authContent: { paddingTop: 54, maxWidth: 460 },
  footer: { paddingHorizontal: 20, paddingBottom: 14, paddingTop: 8, gap: 8, width: '100%', maxWidth: 640, alignSelf: 'center' },
  headingGroup: { gap: 3 },
  brand: { marginBottom: 5, alignSelf: 'flex-start' },
  wordmark: { width: 90, height: 29 },
  title: { color: colors.text, fontSize: 32, fontFamily: fonts.heading },
  heading: { color: colors.text, fontSize: 21, fontFamily: fonts.heading },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, fontFamily: fonts.body },
  label: { color: colors.text, fontSize: 14, fontFamily: fonts.bold },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, minHeight: 50,
    color: colors.text, backgroundColor: colors.surface, fontFamily: fonts.body, fontSize: 15 },
  inputRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 0 },
  inlineInput: { flex: 1, minWidth: 0, borderWidth: 0, paddingHorizontal: 0, backgroundColor: 'transparent' },
  card: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, gap: 12 },
  button: { backgroundColor: colors.darkButton, borderRadius: 9, minHeight: 48, padding: 12, justifyContent: 'center' },
  buttonText: { textAlign: 'center', color: colors.surface, fontSize: 15, fontFamily: fonts.bold },
  outline: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  textButton: { backgroundColor: 'transparent' },
  dangerButton: { backgroundColor: colors.tint },
  danger: { color: colors.danger },
  link: { color: colors.primary },
  disabled: { backgroundColor: colors.coolTint },
  disabledText: { color: colors.muted },
  dimmed: { opacity: 0.55 },
});
