import type { SharePayload } from 'expo-sharing';

export const MAX_PROBE_TEXT_LENGTH = 20_000;
export type ProbeShare = { kind: 'url' | 'text'; value: string };
export type ShareResult = { ok: true; item: ProbeShare } | { ok: false; message: string };

// Investigation only: no fetching, URL normalization, account or persistent queue.
export function inspectShare(payloads: readonly SharePayload[]): ShareResult {
  if (payloads.length !== 1) return { ok: false, message: 'Поделитесь одной ссылкой или одним текстом.' };
  const payload = payloads[0];
  if (payload.shareType !== 'text' && payload.shareType !== 'url') {
    return { ok: false, message: 'Файлы пока не поддерживаются. Можно поделиться ссылкой на PDF.' };
  }
  const value = payload.value.trim();
  if (!value || value.length > MAX_PROBE_TEXT_LENGTH) {
    return { ok: false, message: 'Нужен непустой текст длиной до 20 000 символов для проверки.' };
  }
  let isWebUrl = false;
  try {
    const url = new URL(value);
    isWebUrl = ['http:', 'https:'].includes(url.protocol) && !/\s/.test(value) && !url.username && !url.password;
  } catch { /* Plain text is supported without extracting an embedded URL. */ }
  if (payload.shareType === 'url' && !isWebUrl) return { ok: false, message: 'Для ссылки нужен адрес http или https без пароля.' };
  return { ok: true, item: { kind: isWebUrl ? 'url' : 'text', value } };
}
