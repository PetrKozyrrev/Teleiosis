import { ApiError, AuthApi, type LibraryMethod, type LibraryOptions, type LibraryPath, type Session } from './api';
import type { Vault } from './vault';

export type AuthState = { phase: 'loading' | 'signedOut' | 'signedIn' | 'offline' | 'error'; session: Session | null; busy: boolean; message: string | null; offlineOwner?: number | null };
const safeStorageError = 'Не удалось обратиться к защищённому хранилищу. Разблокируйте устройство и повторите.';

export class AuthController {
  private token: string | null = null;
  private listeners = new Set<() => void>();
  private state: AuthState = { phase: 'loading', session: null, busy: false, message: null };
  constructor(private readonly api: AuthApi, private readonly storage: Vault) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(patch: Partial<AuthState>) { this.state = { ...this.state, ...patch }; this.listeners.forEach(listener => listener()); }

  private async exclusive(task: () => Promise<void>) {
    if (this.state.busy) throw new Error('Дождитесь завершения текущего запроса.');
    this.set({ busy: true, message: null });
    try { await task(); }
    catch (error) {
      const message = error instanceof ApiError ? error.message : safeStorageError;
      this.set({ message });
      throw new Error(message);
    } finally { this.set({ busy: false }); }
  }

  async initialize() {
    await this.exclusive(async () => {
      try {
        await this.storage.initialize();
        if (!this.api.origin) {
          this.set({ phase: 'signedOut', session: null, message: 'Подключение к серверу ещё не настроено в этой сборке.' });
          return;
        }
        this.token = await this.storage.load(this.api.origin);
        if (!this.token) { this.set({ phase: 'signedOut', session: null }); return; }
        const offlineOwner = await this.storage.lastOwner?.(this.api.origin, this.token);
        if (offlineOwner) this.set({ phase: 'offline', offlineOwner });
        await this.refreshSession();
      } catch (error) {
        if (!(error instanceof ApiError)) this.set({ phase: 'error', session: null });
        throw error;
      }
    });
  }

  private async refreshSession() {
    if (!this.token) return;
    try {
      const current = await this.api.current(this.token);
      if (this.storage.lastOwner && this.state.offlineOwner !== current.user.id && this.api.origin) {
        await this.storage.save(this.api.origin, this.token, current.user.id).catch(() => {});
      }
      this.set({ phase: 'signedIn', session: { user: current.user, expires_at: current.expires_at, absolute_expires_at: current.absolute_expires_at }, offlineOwner: current.user.id, message: null });
    }
    catch (error) {
      if (error instanceof ApiError && error.status === 401 && !error.gateway) {
        await this.expireSession();
      } else {
        this.set({ phase: 'offline', message: error instanceof ApiError ? error.message : safeStorageError });
        throw error;
      }
    }
  }

  async refresh() {
    if (this.state.busy || !this.token) return;
    await this.exclusive(() => this.refreshSession());
  }

  verifyGateway = (authorization: string) => this.api.verifyGateway(authorization);

  private async expireSession() {
    this.set({ phase: 'error', session: null, offlineOwner: null });
    await this.storage.clear();
    this.token = null;
    this.set({ phase: 'signedOut', session: null, message: 'Сессия завершилась. Войдите заново.' });
  }

  library = async (path: LibraryPath, method: LibraryMethod, body?: unknown, options?: LibraryOptions) => {
    const token = this.token;
    if (!token) throw new ApiError(401);
    if (!this.state.session) throw new ApiError(this.state.phase === 'offline' ? 0 : 401);
    if (options?.ownerId !== undefined && options.ownerId !== this.state.session.user.id) throw new ApiError(401);
    let response: unknown;
    try {
      response = await this.api.library(path, method, token, body, ...(options ? [options] : []));
    } catch (error) {
      if (token === this.token && error instanceof ApiError && error.status === 401 && !error.gateway) {
        if (this.state.busy) {
          // Let the in-flight auth operation finish before touching SecureStore.
          const unsubscribe = this.subscribe(() => {
            if (this.state.busy) return;
            unsubscribe();
            if (token === this.token && this.state.session) {
              void this.exclusive(() => this.expireSession()).catch(() => {});
            }
          });
        } else {
          await this.exclusive(() => this.expireSession()).catch(() => {});
        }
      }
      throw error;
    }
    if (token !== this.token || !this.state.session) throw new ApiError(401);
    return response;
  };

  async signIn(mode: 'login' | 'register', email: string, password: string, consent?: boolean) {
    if (!this.api.origin) throw new Error('Подключение к серверу ещё не настроено в этой сборке.');
    if (this.token) throw new Error('Сначала завершите текущую сессию на устройстве.');
    await this.exclusive(async () => {
      const issued = await this.api.signIn(mode, email, password, consent);
      try { await this.storage.save(this.api.origin!, issued.token, issued.user.id); }
      catch (error) {
        // Do not report a successful sign-in if durable storage failed.
        try { await this.api.logout(issued.token); } catch { /* Bounded server expiry if offline. */ }
        await this.storage.clear();
        throw error;
      }
      this.token = issued.token;
      this.set({ phase: 'signedIn', session: { user: issued.user, expires_at: issued.expires_at, absolute_expires_at: issued.absolute_expires_at }, offlineOwner: issued.user.id });
    });
  }

  async logout(localOnly = false, beforeClear?: () => Promise<void>) {
    await this.exclusive(async () => {
      if (this.token && !localOnly) {
        try { await this.api.logout(this.token); }
        catch (error) { if (!(error instanceof ApiError && error.status === 401 && !error.gateway)) throw error; }
      }
      await beforeClear?.();
      this.set({ phase: 'error', session: null, offlineOwner: null });
      await this.storage.clear();
      this.token = null;
      this.set({ phase: 'signedOut', session: null });
    });
  }

  async requestVerification() {
    await this.exclusive(async () => {
      if (!this.token) throw new ApiError(401);
      try { await this.api.request('email-verification/request', {}, this.token); }
      catch (error) {
        if (error instanceof ApiError && error.status === 401 && !error.gateway) {
          this.set({ phase: 'error', session: null });
          await this.storage.clear(); this.token = null; this.set({ phase: 'signedOut', session: null });
        }
        throw error;
      }
    });
  }

  async requestReset(email: string) {
    await this.exclusive(async () => { await this.api.request('password-reset/request', { email }); });
  }

  async confirm(kind: 'reset' | 'verify', token: string, password?: string) {
    let warning: string | null = null;
    await this.exclusive(async () => {
      await this.api.request(kind === 'reset' ? 'password-reset/confirm' : 'email-verification/confirm', { token, ...(kind === 'reset' ? { password } : {}) });
      if (kind === 'reset') {
        try { await this.storage.clear(); this.token = null; this.set({ phase: 'signedOut', session: null }); }
        catch {
          this.token = null;
          warning = 'Пароль изменён, но очистка хранилища не подтверждена. Повторите локальный выход на разблокированном устройстве.';
          this.set({ phase: 'error', session: null, message: warning });
        }
      } else if (this.token) {
        try { await this.refreshSession(); }
        catch { warning = 'Адрес подтверждён. Не удалось обновить профиль; повторите проверку сессии.'; }
      }
    });
    return warning;
  }
}
