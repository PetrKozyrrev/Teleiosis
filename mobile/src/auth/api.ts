import { fetch as nativeFetch } from 'expo/fetch';
import { apiOrigin } from './config';

export type User = {
  id: number; email: string; timezone: string;
  reminders_enabled: boolean; reminder_time: string; email_verified_at: string | null;
};
export type Session = { user: User; expires_at: string; absolute_expires_at: string };
export type IssuedSession = Session & { token: string; token_type: 'Bearer' };
export type LibraryPath = '/contents' | '/contents/submissions' | `/contents?${string}` | `/contents/${number}`
  | `/contents/${number}/open` | `/contents/${number}/versioned` | `/contents/${number}/reminder` | '/me' | '/me/settings' | '/me/export' | '/stats' | '/auth/change-password' | '/auth/delete-account' | '/categories' | `/categories/${number}`
  | '/mobile/library/tags' | '/mobile/library/collections'
  | `/mobile/library/tags/${number}` | `/mobile/library/collections/${number}`
  | `/mobile/library/contents/${number}/organization`;
export type LibraryMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
export type LibraryOptions = { ownerId?: number; idempotencyKey?: string; version?: number };

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly gateway = false, public readonly retryAfter: number | null = null,
    public readonly existingId: number | null = null, public readonly code: string | null = null) {
    super(gateway ? 'Проверьте доступ к тестовому стенду.' : status === 401 ? 'Проверьте почту и пароль или войдите заново.'
      : status === 429 ? 'Слишком много попыток. Повторите позже.'
      : status === 409 ? 'Адрес уже зарегистрирован или подтверждён.'
      : status === 422 ? 'Проверьте данные. Пароль должен содержать от 10 до 128 символов.'
      : status === 400 ? 'Ссылка недействительна или срок её действия истёк.'
      : status === 502 ? 'Сервер ответил, но приложение не смогло обработать ответ.'
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
    return this.send(`/mobile/auth/${path}`, body === undefined ? 'GET' : 'POST', body, token);
  }

  async verifyGateway(authorization: string): Promise<void> {
    await this.send('/mobile/auth/session', 'GET', undefined, undefined, authorization);
  }

  library(path: LibraryPath, method: LibraryMethod, token: string, body?: unknown, options?: LibraryOptions) {
    return this.send(path, method, body, token, undefined, options);
  }

  private async send(path: string, method: LibraryMethod, body?: unknown, token?: string,
    gatewayProbe?: string, options?: LibraryOptions): Promise<unknown> {
    if (!this.origin) throw new Error('Подключение к серверу ещё не настроено в этой сборке.');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);
    try {
      const gateway = gatewayProbe ?? await this.gateway();
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (token) headers.Authorization = `Bearer ${token}`;
      if (gateway) headers['X-Staging-Authorization'] = gateway;
      if (options?.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
      if (options?.version !== undefined) headers['If-Match'] = `"${options.version}"`;
      const response = await this.transport(`${this.origin}${path}`, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
        credentials: 'omit', redirect: 'error', signal: controller.signal,
      });
      const basicChallenge = /^basic\b/i.test(response.headers.get('WWW-Authenticate') ?? '');
      if (gatewayProbe !== undefined) {
        if (response.status === 401 && basicChallenge) throw new ApiError(401, true);
        // With a valid gateway password and no app token, the staging API returns 401.
        if (response.status === 401 && response.headers.get('X-Teleiosis-Environment') === 'staging') return;
        throw new ApiError(502);
      }
      if (!response.ok) {
        const retry = Number(response.headers.get('Retry-After'));
        let existingId = null;
        if (response.status === 409 && method === 'POST' && (path === '/contents' || path === '/contents/submissions')) {
          const result = await response.json().catch(() => null);
          const id = result?.detail?.existing_id;
          if (Number.isSafeInteger(id) && id > 0) existingId = id;
        }
        let code: string | null = null;
        if (response.status === 409 && path.startsWith('/mobile/library/')) {
          const result = await response.json().catch(() => null);
          if (['group_name_exists', 'group_limit_reached'].includes(result?.detail?.code)) code = result.detail.code;
        }
        throw new ApiError(response.status, basicChallenge,
          Number.isFinite(retry) && retry > 0 ? Math.min(retry, 3600) : null, existingId, code);
      }
      if (response.status === 204) return;
      try {
        return await response.json();
      } catch {
        throw new ApiError(502);
      }
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
