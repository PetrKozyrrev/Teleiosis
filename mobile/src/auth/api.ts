import { fetch as nativeFetch } from 'expo/fetch';
import { apiOrigin } from './config';

export type User = {
  id: number; email: string; timezone: string;
  reminders_enabled: boolean; reminder_time: string; email_verified_at: string | null;
};
export type Session = { user: User; expires_at: string; absolute_expires_at: string };
export type IssuedSession = Session & { token: string; token_type: 'Bearer' };

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly gateway = false, public readonly retryAfter: number | null = null) {
    super(gateway ? 'Проверьте доступ к тестовому стенду.' : status === 401 ? 'Проверьте почту и пароль или войдите заново.'
      : status === 429 ? 'Слишком много попыток. Повторите позже.'
      : status === 409 ? 'Адрес уже зарегистрирован или подтверждён.'
      : status === 422 ? 'Проверьте данные. Пароль должен содержать от 10 до 128 символов.'
      : status === 400 ? 'Ссылка недействительна или срок её действия истёк.'
      : status === 0 ? 'Не удалось связаться с сервером. Проверьте подключение и повторите.'
      : 'Не удалось выполнить запрос. Повторите позже.');
  }
}

function session(value: unknown): Session {
  const s = value as Partial<Session> | null;
  if (!s || !s.user || !Number.isSafeInteger(s.user.id) || s.user.id <= 0 || typeof s.user.email !== 'string'
      || typeof s.user.timezone !== 'string' || typeof s.user.reminders_enabled !== 'boolean'
      || typeof s.user.reminder_time !== 'string' || !(s.user.email_verified_at === null || typeof s.user.email_verified_at === 'string')
      || typeof s.expires_at !== 'string' || !Number.isFinite(Date.parse(s.expires_at))
      || typeof s.absolute_expires_at !== 'string' || !Number.isFinite(Date.parse(s.absolute_expires_at))) throw new ApiError(502);
  return { user: s.user, expires_at: s.expires_at, absolute_expires_at: s.absolute_expires_at };
}

export class AuthApi {
  constructor(readonly origin: string | null, private readonly gateway: () => Promise<string | null>, private readonly transport: typeof nativeFetch = nativeFetch) {
    this.origin = apiOrigin(origin ?? undefined);
  }

  async request(path: string, body?: unknown, token?: string): Promise<unknown> {
    if (!this.origin) throw new Error('Подключение к серверу ещё не настроено в этой сборке.');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);
    try {
      const gateway = await this.gateway();
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (token) headers.Authorization = `Bearer ${token}`;
      if (gateway) headers['X-Staging-Authorization'] = gateway;
      const response = await this.transport(`${this.origin}/mobile/auth/${path}`, {
        method: body === undefined ? 'GET' : 'POST', headers, body: body === undefined ? undefined : JSON.stringify(body),
        credentials: 'omit', redirect: 'error', signal: controller.signal,
      });
      if (!response.ok) {
        const retry = Number(response.headers.get('Retry-After'));
        throw new ApiError(response.status, /^basic\b/i.test(response.headers.get('WWW-Authenticate') ?? ''),
          Number.isFinite(retry) && retry > 0 ? Math.min(retry, 3600) : null);
      }
      return response.status === 204 ? undefined : await response.json();
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(0);
    } finally { clearTimeout(timeout); }
  }

  async signIn(mode: 'login' | 'register', email: string, password: string, consent = false): Promise<IssuedSession> {
    const result = await this.request(mode, { email, password, ...(mode === 'register' ? { consent, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone } : {}) });
    const s = session(result);
    const issued = result as IssuedSession;
    if (issued.token_type !== 'Bearer' || !/^[A-Za-z0-9_-]{16,128}$/.test(issued.token)) throw new ApiError(502);
    return { ...s, token: issued.token, token_type: 'Bearer' };
  }

  async current(token: string): Promise<Session> { return session(await this.request('session', undefined, token)); }
  async logout(token: string): Promise<void> { await this.request('logout', {}, token); }
}
