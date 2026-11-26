import { afterEach, beforeEach, expect, jest, test } from '@jest/globals';
import type { Request } from '../src/library/model';

jest.mock('expo-crypto', () => ({
  randomUUID: jest.requireActual<typeof import('node:crypto')>('node:crypto').randomUUID,
}));

const original = process.env.EXPO_PUBLIC_LEARNING_METRICS;
const owner = 'https://example.com/42';

function recorder() {
  return jest.requireActual<typeof import('../src/learning/events')>('../src/learning/events').trackLearning;
}

beforeEach(() => {
  jest.resetModules();
  delete process.env.EXPO_PUBLIC_LEARNING_METRICS;
});

afterEach(() => {
  if (original !== undefined) process.env.EXPO_PUBLIC_LEARNING_METRICS = original;
  else delete process.env.EXPO_PUBLIC_LEARNING_METRICS;
  jest.restoreAllMocks();
});

test('the build flag starts disabled and owner is kept out of the request body', () => {
  const request = jest.fn<Request>().mockResolvedValue(undefined);
  const track = recorder();
  track(request, owner, { name: 'today_viewed' });
  expect(request).not.toHaveBeenCalled();

  process.env.EXPO_PUBLIC_LEARNING_METRICS = '1';
  track(request, owner, { name: 'today_viewed' });
  track(request, owner, { name: 'today_viewed' });
  expect(request).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenCalledWith('/mobile/learning/events', 'POST',
    { name: 'today_viewed', visit_id: expect.any(String) }, { idempotencyKey: expect.any(String) });
});

test('reuses a failed receipt and rotates the visit after inactivity or account change', async () => {
  process.env.EXPO_PUBLIC_LEARNING_METRICS = '1';
  const clock = jest.spyOn(Date, 'now').mockReturnValue(1_000_000);
  const request = jest.fn<Request>().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined);
  const track = recorder();
  const action = { name: 'recommendation_opened', material_id: 12, budget_minutes: 15 } as const;
  track(request, owner, action);
  await Promise.resolve();
  track(request, owner, action);
  expect(request.mock.calls[0]).toEqual(request.mock.calls[1]);
  clock.mockReturnValue(1_000_000 + 30 * 60 * 1000);
  track(request, owner, action);
  track(request, 'https://example.com/84', action);
  const visits = request.mock.calls.map(([, , payload]) => (payload as { visit_id: string }).visit_id);
  expect(new Set(visits).size).toBe(3);
});
