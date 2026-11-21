import { expect, jest, test } from '@jest/globals';
import { fetch as nativeFetch } from 'expo/fetch';
import { AuthApi } from '../src/auth/api';

jest.mock('expo/fetch', () => ({ fetch: jest.fn() }));

test('sends one native library request with separate credentials and decodes duplicate ID', async () => {
  const transport = jest.fn<typeof nativeFetch>().mockResolvedValue({
    ok: false, status: 409, headers: new Headers(),
    json: async () => ({ detail: { message: 'Already saved', existing_id: 17 } }),
  } as Awaited<ReturnType<typeof nativeFetch>>);
  const api = new AuthApi('https://example.com', async () => 'Basic synthetic', transport);
  const body = { url: 'https://example.com/sample.pdf' };
  await expect(api.library('/contents', 'POST', 'synthetic-session', body)).rejects.toMatchObject({ status: 409, existingId: 17 });
  expect(transport).toHaveBeenCalledTimes(1);
  expect(transport).toHaveBeenCalledWith('https://example.com/contents', expect.objectContaining({
    method: 'POST', credentials: 'omit', redirect: 'error', body: JSON.stringify(body),
    headers: {
      Accept: 'application/json', 'Content-Type': 'application/json',
      Authorization: 'Bearer synthetic-session', 'X-Staging-Authorization': 'Basic synthetic',
    },
  }));
});

test('sends the UUID and version in the dedicated write endpoints', async () => {
  const transport = jest.fn<typeof nativeFetch>().mockResolvedValue({
    ok: true, status: 201, headers: new Headers(), json: async () => ({ id: 17, version: 1 }),
  } as Awaited<ReturnType<typeof nativeFetch>>);
  const api = new AuthApi('https://example.com', async () => null, transport);
  const key = 'a3adc2ca-b49c-4c7e-9b38-003189ffddf9';
  await api.library('/contents/submissions', 'POST', 'synthetic-session', { note: 'Synthetic note' }, { idempotencyKey: key });
  await api.library('/contents/17/versioned', 'PATCH', 'synthetic-session', { title: 'Synthetic title' }, { version: 1 });

  expect(transport).toHaveBeenNthCalledWith(1, 'https://example.com/contents/submissions', expect.objectContaining({
    method: 'POST', headers: expect.objectContaining({ 'Idempotency-Key': key }),
  }));
  expect(transport).toHaveBeenNthCalledWith(2, 'https://example.com/contents/17/versioned', expect.objectContaining({
    method: 'PATCH', headers: expect.objectContaining({ 'If-Match': '"1"' }),
  }));
});

test('organization uses mobile gateway aliases, preserves Bearer and If-Match, and does not replay POST', async () => {
  const transport = jest.fn<typeof nativeFetch>().mockResolvedValue({
    ok: false, status: 409, headers: new Headers(), json: async () => ({ detail: { code: 'group_limit_reached' } }),
  } as Awaited<ReturnType<typeof nativeFetch>>);
  const api = new AuthApi('https://example.com', async () => 'Basic synthetic', transport);
  await expect(api.library('/mobile/library/tags', 'POST', 'synthetic-session', { name: 'Synthetic' }))
    .rejects.toMatchObject({ status: 409, code: 'group_limit_reached' });
  expect(transport).toHaveBeenCalledTimes(1);
  await expect(api.library('/mobile/library/contents/17/organization', 'PATCH', 'synthetic-session', { tag_ids: [] }, { version: 3 }))
    .rejects.toMatchObject({ status: 409 });
  expect(transport).toHaveBeenLastCalledWith('https://example.com/mobile/library/contents/17/organization', expect.objectContaining({
    credentials: 'omit', redirect: 'error', headers: expect.objectContaining({
      Authorization: 'Bearer synthetic-session', 'X-Staging-Authorization': 'Basic synthetic', 'If-Match': '"3"',
    }),
  }));
});
