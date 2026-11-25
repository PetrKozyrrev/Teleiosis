import Storage from 'expo-sqlite/kv-store';
import { useEffect, useState, useSyncExternalStore } from 'react';
import english from './en.json';

export type Language = 'ru' | 'en';
export const languageNames: Record<Language, string> = { ru: 'Русский', en: 'English' };
const storageKey = 'app.language';
const catalog: Readonly<Record<string, string>> = english;
const listeners = new Set<() => void>();
let language: Language = 'ru';
let initialization: Promise<void> | undefined;

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function currentLanguage() { return language; }
function defaultLanguage(): Language { return 'ru'; }

function applyLanguage(value: Language) {
  if (value === language) return;
  language = value;
  for (const listener of listeners) listener();
}

function loadLanguage() {
  initialization ??= Storage.getItem(storageKey).then(saved => {
    if (saved === 'ru' || saved === 'en') applyLanguage(saved);
  }).catch(() => { /* A failed read leaves the default language available. */ });
  return initialization;
}

export async function saveLanguage(value: Language) {
  await loadLanguage();
  await Storage.setItem(storageKey, value);
  applyLanguage(value);
}

export function useLanguageReady() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    void loadLanguage().then(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, []);
  return ready;
}

export function useLanguage() {
  return useSyncExternalStore(subscribe, currentLanguage, defaultLanguage);
}

type Value = string | number;
type Translation = (text: string, ...values: Value[]) => string;

function interpolate(text: string, values: Value[]) {
  return values.length ? text.replace(/\{(\d+)\}/g, (key, index) => String(values[Number(index)] ?? key)) : text;
}

const translations: Record<Language, Translation> = {
  ru: (text, ...values) => interpolate(text, values),
  en: (text, ...values) => interpolate(Object.hasOwn(catalog, text) ? catalog[text] : text, values),
};

export function useTranslation() { return translations[useLanguage()]; }

export function translate(text: string, ...values: Value[]) { return translations[language](text, ...values); }

export function useLocale() { return useLanguage() === 'en' ? 'en-US' : 'ru-RU'; }
