export type EmailAction = { kind: 'reset' | 'verify'; token: string; validUntil: number; id: number };
let pending: EmailAction | null = null;
let nextId = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

export function parseEmailLink(path: string, origin: string | null): Omit<EmailAction, 'validUntil' | 'id'> | null {
  try {
    if (!origin) return null;
    const url = new URL(path);
    if (url.protocol !== 'https:' || url.origin !== origin || url.username || url.password || url.search) return null;
    const kind = url.pathname === '/app/reset.html' ? 'reset' : url.pathname === '/app/verify.html' ? 'verify' : null;
    const params = new URLSearchParams(url.hash.slice(1));
    const token = params.get('token');
    if (!kind || params.getAll('token').length !== 1 || !token || !/^[A-Za-z0-9_-]{16,128}$/.test(token)) return null;
    return { kind, token };
  } catch { return null; }
}

export function clearEmailAction(expectedId?: number) {
  if (expectedId !== undefined && pending?.id !== expectedId) return;
  pending = null;
  if (timer) clearTimeout(timer);
  timer = null;
  listeners.forEach(listener => listener());
}

export function receiveEmailLink(path: string, origin: string | null): boolean {
  clearEmailAction();
  const parsed = parseEmailLink(path, origin);
  if (!parsed) return false;
  const id = ++nextId;
  pending = { ...parsed, validUntil: Date.now() + 30 * 60_000, id };
  timer = setTimeout(() => clearEmailAction(id), 30 * 60_000);
  listeners.forEach(listener => listener());
  return true;
}

export const emailActionSnapshot = () => pending && pending.validUntil > Date.now() ? pending : null;
export const subscribeEmailActions = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};
