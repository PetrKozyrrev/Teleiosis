import { describe, expect, jest, test } from '@jest/globals';
import { fetch as nativeFetch } from 'expo/fetch';
import { ApiError, AuthApi } from '../src/auth/api';
import { apiOrigin } from '../src/auth/config';

jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));
const profile = { id: 1, email: 'user@example.com', timezone: 'UTC', reminders_enabled: true, reminder_time: '10:00', email_verified_at: null };
const issued = { user: profile, token: 'a'.repeat(43), token_type: 'Bearer', expires_at: '2026-12-01T00:00:00Z', absolute_expires_at: '2027-01-01T00:00:00Z' };
function response(status: number, json: unknown, headers: Record<string, string> = {}, readJson = async () => json) {
  return { ok: status >= 200 && status < 300, status, json: readJson, headers: { get: (key: string) => headers[key] ?? null } } as Awaited<ReturnType<typeof nativeFetch>>;
}

describe('native credential transport', () => {
  test.each(['http://example.com', 'https://user:secret@example.com', 'https://example.com/path', 'https://example.com/?q=token', 'https://example.com/#token'])('refuses unsafe API origins %s', value => {
    expect(() => apiOrigin(value)).toThrow();
  });
  test('omits cookies, refuses redirects and sends no Bearer during login', async () => {
    const transport = jest.fn<typeof nativeFetch>().mockResolvedValue(response(200, issued));
    const api = new AuthApi('https://example.com', async () => 'Basic synthetic-gate', transport);
    expect((await api.signIn('login', profile.email, 'password')).token).toBe(issued.token);
    const [url, init] = transport.mock.calls[0];
    expect(url).toBe('https://example.com/mobile/auth/login');
    expect(init).toMatchObject({ method: 'POST', credentials: 'omit', redirect: 'error', headers: { 'X-Staging-Authorization': 'Basic synthetic-gate' } });
    expect(init?.headers).not.toHaveProperty('Authorization');
    expect(init?.headers).not.toHaveProperty('Origin');
  });
  test('Bearer is used only for an authenticated request; response does not retain extra token fields', async () => {
    const transport = jest.fn<typeof nativeFetch>().mockResolvedValue(response(200, issued));
    const api = new AuthApi('https://example.com', async () => null, transport);
    expect(await api.current(issued.token)).not.toHaveProperty('token');
    expect(transport.mock.calls[0][1]?.headers).toMatchObject({ Authorization: `Bearer ${issued.token}` });
  });
  test('gateway 401 is distinguishable from an expired app session and response text is ignored', async () => {
    const transport = jest.fn<typeof nativeFetch>().mockResolvedValue(response(401, { detail: 'private token internals' }, { 'WWW-Authenticate': 'Basic realm="test"' }));
    const api = new AuthApi('https://example.com', async () => null, transport);
    await expect(api.current(issued.token)).rejects.toMatchObject({ status: 401, gateway: true });
    await expect(api.current(issued.token)).rejects.not.toThrow('private token internals');
  });
  test('verifies the candidate gateway password without sending a session or touching saved credentials', async () => {
    const body = jest.fn<() => Promise<never>>().mockRejectedValue(new Error('Cannot read response body'));
    const transport = jest.fn<typeof nativeFetch>().mockResolvedValue(response(401, null, { 'X-Teleiosis-Environment': 'staging' }, body));
    const saved = jest.fn<() => Promise<string | null>>();
    const api = new AuthApi('https://example.com', saved, transport);
    await expect(api.verifyGateway('Basic candidate')).resolves.toBeUndefined();
    expect(saved).not.toHaveBeenCalled();
    expect(body).not.toHaveBeenCalled();
    expect(transport).toHaveBeenCalledWith('https://example.com/mobile/auth/session', expect.objectContaining({ method: 'GET', headers: { Accept: 'application/json', 'X-Staging-Authorization': 'Basic candidate' } }));
    transport.mockResolvedValue(response(401, {}, { 'WWW-Authenticate': 'Basic realm="test"' }));
    await expect(api.verifyGateway('Basic candidate')).rejects.toMatchObject({ status: 401, gateway: true });
    transport.mockResolvedValue(response(401, { detail: 'Not authenticated' }));
    await expect(api.verifyGateway('Basic candidate')).rejects.toMatchObject({ status: 502 });
  });

  test('reports an unreadable response separately from a network failure', async () => {
    const body = jest.fn<() => Promise<never>>().mockRejectedValue(new Error('Cannot read response body'));
    const transport = jest.fn<typeof nativeFetch>().mockResolvedValue(response(200, null, {}, body));
    const api = new AuthApi('https://example.com', async () => null, transport);
    await expect(api.signIn('login', profile.email, 'password')).rejects.toMatchObject({ status: 502 });
  });
  test('does not retry passwords on network, server errors or rate limit', async () => {
    const transport = jest.fn<typeof nativeFetch>().mockResolvedValue(response(429, {}, { 'Retry-After': '60' }));
    const api = new AuthApi('https://example.com', async () => null, transport);
    await expect(api.signIn('login', profile.email, 'password')).rejects.toMatchObject({ status: 429, retryAfter: 60 });
    expect(transport).toHaveBeenCalledTimes(1);
    transport.mockRejectedValue(new Error('secret transport internals'));
    await expect(api.current(issued.token)).rejects.toEqual(new ApiError(0));
    expect(transport).toHaveBeenCalledTimes(2);
  });
  test('rejects malformed successful authentication data', async () => {
    const transport = jest.fn<typeof nativeFetch>().mockResolvedValue(response(200, { ...issued, token: 'not a token' }));
    await expect(new AuthApi('https://example.com', async () => null, transport).signIn('login', profile.email, 'password')).rejects.toMatchObject({ status: 502 });
  });
});
