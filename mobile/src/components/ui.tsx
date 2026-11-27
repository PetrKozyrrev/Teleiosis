import type { ComponentRef, PropsWithChildren, ReactNode, Ref } from 'react';
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type StyleProp, type TextInputProps, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, fonts } from '../theme';

export function Page({ title, subtitle, brand, auth, headingAction, footer, insetFooter, children, scrollRef, keyboardOffset, revealFocusedField }: PropsWithChildren<{
  title: string; subtitle?: string; brand?: boolean; auth?: boolean; footer?: ReactNode;
  headingAction?: ReactNode; insetFooter?: boolean;
  scrollRef?: Ref<ComponentRef<typeof ScrollView>>;
  keyboardOffset?: number;
  revealFocusedField?: () => void;
}>) {
  const avoidKeyboard = Platform.OS === 'ios' || (Platform.OS === 'android' && keyboardOffset !== undefined);
  return <KeyboardAvoidingView style={[styles.page, auth && styles.auth]} behavior={avoidKeyboard ? 'padding' : undefined}
    keyboardVerticalOffset={keyboardOffset ?? (brand || auth ? 0 : 48)}>
    <ScrollView ref={scrollRef} keyboardShouldPersistTaps="handled" onKeyboardDidShow={revealFocusedField} onLayout={revealFocusedField}
      style={styles.scroll} contentContainerStyle={[styles.content, auth && styles.authContent]}>
    {brand && <Wordmark />}
    <View style={headingAction ? styles.headingRow : undefined}>
      <View style={[styles.headingGroup, Boolean(headingAction) && styles.headingWithAction]}>
        <Text accessibilityRole="header" style={styles.title}>{title}</Text>
        {subtitle && <Body>{subtitle}</Body>}
      </View>
      {headingAction}
    </View>
    {children}
    </ScrollView>
    {footer && (insetFooter
      ? <SafeAreaView edges={{ bottom: 'maximum' }} style={styles.footer}>{footer}</SafeAreaView>
      : <View style={styles.footer}>{footer}</View>)}
  </KeyboardAvoidingView>;
}

export function Wordmark() {
  return <Image source={require('../../assets/teleiosis-wordmark.png')} style={styles.wordmark}
    resizeMode="contain" accessibilityLabel="Teleiosis" accessible />;
}

export function BrandToggle({ label, checked, onChange, disabled = false, role = 'switch' }: {
  label: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean; role?: 'switch' | 'checkbox';
}) {
  return <Pressable accessibilityLabel={label} accessibilityRole={role} accessibilityState={{ checked, disabled }}
    disabled={disabled} onPress={() => onChange(!checked)} style={[styles.toggleTarget, disabled && styles.dimmed]}>
    {role === 'checkbox'
      ? <View style={[styles.checkbox, checked && styles.toggleOn]}>{checked && <Text style={styles.checkmark}>✓</Text>}</View>
      : <View style={[styles.track, checked && styles.toggleOn, checked && styles.checkedTrack]}><View style={styles.thumb} /></View>}
  </Pressable>;
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

export function Card({ children, featured, compact, onPress }: PropsWithChildren<{
  featured?: boolean; compact?: boolean; onPress?: () => void;
}>) {
  const cardStyles = [styles.card, featured && styles.featuredCard, compact && styles.compactCard];
  if (onPress) return <Pressable accessibilityRole="button" onPress={onPress}
    style={({ pressed }) => [...cardStyles, pressed && styles.dimmed]}>{children}</Pressable>;
  return <View style={cardStyles}>{children}</View>;
}

export function Body({ children }: PropsWithChildren) {
  return <Text style={styles.body}>{children}</Text>;
}

export function Action({ title, onPress, disabled = false, variant = 'primary', selected, style, accessibilityLabel }: {
  title: string; onPress: () => void; disabled?: boolean; variant?: 'primary' | 'outline' | 'text' | 'danger';
  selected?: boolean; style?: StyleProp<ViewStyle>; accessibilityLabel?: string;
}) {
  return <Pressable accessibilityRole="button" accessibilityLabel={accessibilityLabel} accessibilityState={{ disabled, selected }}
    disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.button, variant === 'outline' && styles.outline, variant === 'text' && styles.textButton,
      variant === 'danger' && styles.dangerButton, disabled && styles.disabled, pressed && styles.dimmed, style]}>
    <Text style={[styles.buttonText, variant === 'outline' && styles.label, variant === 'text' && styles.link,
      variant === 'danger' && styles.danger, disabled && styles.disabledText]}>{title}</Text>
  </Pressable>;
}

export const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  scroll: { flex: 1 },
  auth: { backgroundImage: 'linear-gradient(154deg, #FBF7FB 0%, #DEEAF1 42%, #EDDCEB 100%)' },
  content: { paddingHorizontal: 20, paddingTop: 12, gap: 16, paddingBottom: 24, width: '100%', maxWidth: 640, alignSelf: 'center' },
  authContent: { paddingTop: 54, maxWidth: 460 },
  footer: { paddingHorizontal: 20, paddingBottom: 14, paddingTop: 8, gap: 8, width: '100%', maxWidth: 640, alignSelf: 'center' },
  headingGroup: { gap: 3 },
  headingRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  headingWithAction: { flexGrow: 1 },
  wordmark: { width: 90, height: 29, marginBottom: 5, alignSelf: 'flex-start' },
  toggleTarget: { minWidth: 48, minHeight: 48, alignItems: 'center', justifyContent: 'center' },
  checkbox: { width: 24, height: 24, borderRadius: 6, borderWidth: 1, borderColor: colors.muted, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  checkmark: { color: colors.surface, fontSize: 16, fontFamily: fonts.bold },
  track: { width: 44, height: 26, padding: 3, borderRadius: 13, backgroundColor: colors.muted, justifyContent: 'center' },
  toggleOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkedTrack: { alignItems: 'flex-end' },
  thumb: { width: 20, height: 20, borderRadius: 10, backgroundColor: colors.surface },
  title: { color: colors.text, fontSize: 32, fontFamily: fonts.heading },
  heading: { color: colors.text, fontSize: 21, fontFamily: fonts.heading },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, fontFamily: fonts.body },
  label: { color: colors.text, fontSize: 14, fontFamily: fonts.bold },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, minHeight: 50,
    color: colors.text, backgroundColor: colors.surface, fontFamily: fonts.body, fontSize: 15 },
  inputRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 0 },
  inlineInput: { flex: 1, minWidth: 0, borderWidth: 0, paddingHorizontal: 0, backgroundColor: 'transparent' },
  card: { backgroundColor: colors.surface, borderRadius: 16, padding: 16, gap: 12 },
  featuredCard: { borderWidth: 1, borderColor: colors.primary },
  compactCard: { gap: 4 },
  button: { backgroundColor: colors.primary, borderRadius: 9, minHeight: 48, padding: 12, justifyContent: 'center' },
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
