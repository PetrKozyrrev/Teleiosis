import { expect, test, jest, afterEach } from '@jest/globals';
import { reminderInstant } from '../src/account/reminderTime';

afterEach(() => { jest.useRealTimers(); });
test('requires an explicit offset and distinguishes repeated DST times', () => {
  jest.useFakeTimers().setSystemTime(new Date('2026-01-01T00:00:00Z'));
  expect(reminderInstant('2026-10-25T02:30+02:00')).toBe('2026-10-25T00:30:00.000Z');
  expect(reminderInstant('2026-10-25T02:30+01:00')).toBe('2026-10-25T01:30:00.000Z');
  expect(() => reminderInstant('2026-10-25T02:30')).toThrow();
  expect(() => reminderInstant('2026-02-30T10:00Z')).toThrow();
  expect(() => reminderInstant('2025-12-31T10:00Z')).toThrow();
});
