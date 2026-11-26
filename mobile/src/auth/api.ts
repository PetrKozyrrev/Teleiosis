import { fetch as nativeFetch } from 'expo/fetch';
import { apiOrigin } from './config';

export type User = {
  id: number; email: string; timezone: string;
  reminders_enabled: boolean; reminder_time: string; email_verified_at: string | null;
};
export type Profile = User & { display_name: string | null; weekly_reading_goal: number };
export type Session = { user: User; expires_at: string; absolute_expires_at: string };
export type IssuedSession = Session & { token: string; token_type: 'Bearer' };
type ImportPath = '/mobile/library/imports/preview' | '/mobile/library/imports/apply';
type PdfPath = '/mobile/library/pdf' | `/mobile/library/pdf?${string}`
  | `/mobile/library/contents/${number}/pdf` | `/mobile/library/contents/${number}/pdf/download`;
type PlanPath = '/mobile/plan' | `/mobile/plan?day=${string}` | '/mobile/plan/goals' | `/mobile/plan/goals/${number}`
  | '/mobile/plan/tasks' | `/mobile/plan/tasks/${number}` | `/mobile/plan/tasks/${number}/${'day' | 'complete'}`
  | `/mobile/plan/weeks/${string}/budget`;
type ReviewPath = '/mobile/review' | `/mobile/review?${string}` | `/mobile/review/${number}`
  | `/mobile/review/${number}/answers` | `/mobile/review/${number}/history?${string}`;
type GoalPath = '/mobile/learning/goals' | `/mobile/learning/goals?${string}` | `/mobile/learning/goals/${number}`
  | `/mobile/learning/goals/${number}/materials` | `/mobile/learning/goals/${number}/materials?${string}`
  | `/mobile/learning/goals/${number}/materials/${number}`;
type CompletionPath = `/mobile/learning/materials/${number}/${'completion' | 'reflection'}`;
export type LibraryPath = ReviewPath | PlanPath | GoalPath | CompletionPath | '/contents' | '/contents/submissions' | '/mobile/library/submissions' | `/contents?${string}` | `/contents/${number}`
  | '/mobile/profile' | `/mobile/reading-progress?${string}` | '/mobile/library/link-preview' | '/mobile/learning/today'
  | `/mobile/learning/time-budget?budget_minutes=${5 | 15 | 30 | 60}`
  | '/mobile/learning/events'
  | `/contents/${number}/open` | `/contents/${number}/versioned` | `/contents/${number}/reminder` | '/me' | '/me/settings' | '/me/export' | '/stats' | '/auth/change-password' | '/auth/delete-account' | '/categories' | `/categories/${number}`
  | '/mobile/library/tags' | '/mobile/library/collections'
  | `/mobile/library/tags/${number}` | `/mobile/library/collections/${number}`
  | `/mobile/library/contents/${number}/organization` | `/mobile/library/search?${string}` | ImportPath | PdfPath;
export type LibraryMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
export type LibraryOptions = { ownerId?: number; idempotencyKey?: string; version?: number; pdfFilename?: string; pdfTitle?: string };

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly gateway = false, public readonly retryAfter: number | null = null,
    public readonly existingId: number | null = null, public readonly code: string | null = null,
    public readonly location: (string | number)[] = []) {
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
    const pdf = /^\/mobile\/library\/(?:pdf(?:\?.*)?|contents\/\d+\/pdf(?:\/download)?)$/.test(path);
    const download = pdf && path.endsWith('/download');
    const timeout = setTimeout(() => controller.abort(), pdf ? 45_000 : 20_000);
    try {
      const gateway = gatewayProbe ?? await this.gateway();
      const importFile = path === '/mobile/library/imports/preview' || path === '/mobile/library/imports/apply';
      const headers: Record<string, string> = { Accept: download ? 'application/pdf' : 'application/json' };
      if (body !== undefined) headers['Content-Type'] = pdf ? 'application/pdf' : 'application/json';
      if (pdf && options?.pdfFilename) headers['X-Teleiosis-Filename'] = encodeURIComponent(options.pdfFilename);
      if (pdf && options?.pdfTitle) headers['X-Teleiosis-Pdf-Title'] = encodeURIComponent(options.pdfTitle);
      if (token) headers.Authorization = `Bearer ${token}`;
      if (gateway) headers['X-Staging-Authorization'] = gateway;
      if (options?.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
      if (options?.version !== undefined) headers['If-Match'] = `"${options.version}"`;
      const response = await this.transport(`${this.origin}${path}`, {
        method, headers, body: (importFile || pdf) && body instanceof ArrayBuffer
          ? body : body === undefined ? undefined : JSON.stringify(body),
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
        const submission = path === '/contents/submissions' || path === '/mobile/library/submissions';
        if (response.status === 409 && ((method === 'POST' && (path === '/contents' || submission)) || path.endsWith('/versioned'))) {
          const result = await response.json().catch(() => null);
          const id = result?.detail?.existing_id;
          if (Number.isSafeInteger(id) && id > 0) existingId = id;
        }
        let code: string | null = null;
        let location: (string | number)[] = [];
        if ((importFile && [409, 413, 415, 422].includes(response.status))
          || (path === '/mobile/auth/register' && response.status === 422)
          || (response.status === 404 && (submission || path.endsWith('/versioned')))
          || (pdf && !basicChallenge)
          || (response.status === 409 && (path.startsWith('/mobile/library/') || path.startsWith('/mobile/plan/')))
          || (path.startsWith('/mobile/learning/') && [404, 409, 412].includes(response.status))) {
          const result = await response.json().catch(() => null);
          const issue = Array.isArray(result?.detail) && result.detail.length === 1 ? result.detail[0] : null;
          if (path === '/mobile/auth/register' && issue?.type === 'extra_forbidden'
            && Array.isArray(issue.loc) && issue.loc.length === 2 && issue.loc[0] === 'body' && issue.loc[1] === 'display_name') {
            code = 'registration_name_unsupported';
          }
          if (result?.detail?.code === 'collection_missing') code = result.detail.code;
          if (path === '/mobile/library/submissions' && response.status === 404 && result?.detail === 'Category not found') code = 'category_missing';
          if (['group_name_exists', 'group_limit_reached'].includes(result?.detail?.code)) code = result.detail.code;
          if (path.startsWith('/mobile/plan/') && ['already_planned', 'goal_limit', 'task_completed', 'goal_archive_required'].includes(result?.detail?.code)) code = result.detail.code;
          if (path.startsWith('/mobile/learning/') && ['completion_task_missing', 'completion_key_reused',
            'reflection_version_changed', 'content_version_changed', 'goal_limit', 'goal_name_taken'].includes(result?.detail?.code)) code = result.detail.code;
          if (pdf && /^(pdf_[a-z_]+|invalid_pdf(?:_name|_title)?|unsafe_pdf|unsupported_pdf)$/.test(result?.detail?.code)) {
            code = result.detail.code;
          }
          if (importFile && typeof result?.detail?.code === 'string') {
            code = result.detail.code;
            if (Array.isArray(result.detail.location)) {
              location = result.detail.location.slice(0, 3).filter((part: unknown) =>
                (typeof part === 'string' && /^[a-z_]{1,32}$/.test(part)) ||
                (typeof part === 'number' && Number.isSafeInteger(part) && part >= 0));
            }
          }
        }
        throw new ApiError(response.status, basicChallenge,
          Number.isFinite(retry) && retry > 0 ? Math.min(retry, 3600) : null, existingId, code, location);
      }
      if (response.status === 204) return;
      if (download) {
        const size = Number(response.headers.get('Content-Length'));
        if (response.headers.get('Content-Type')?.split(';')[0] !== 'application/pdf' ||
          !Number.isInteger(size) || size < 1 || size > 10 * 1024 * 1024) throw new ApiError(502);
        const file = await response.arrayBuffer();
        if (file.byteLength !== size) throw new ApiError(502);
        return file;
      }
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

  async signIn(mode: 'login' | 'register', email: string, password: string, consent = false, displayName?: string): Promise<IssuedSession> {
    const body = { email, password, ...(mode === 'register' ? {
      consent, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    } : {}) };
    const name = mode === 'register' ? displayName : undefined;
    const result = await this.request(mode, name ? { ...body, display_name: name } : body).catch((error: unknown) => {
      // The older API rejects this field during validation, before creating an account.
      if (name && error instanceof ApiError && error.code === 'registration_name_unsupported') return this.request(mode, body);
      throw error;
    });
    const s = session(result);
    const issued = result as IssuedSession;
    if (issued.token_type !== 'Bearer' || !/^[A-Za-z0-9_-]{16,128}$/.test(issued.token)) throw new ApiError(502);
    return { ...s, token: issued.token, token_type: 'Bearer' };
  }

  async current(token: string): Promise<Session> { return session(await this.request('session', undefined, token)); }
  async logout(token: string): Promise<void> { await this.request('logout', {}, token); }
}
