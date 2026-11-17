import { afterEach, expect, jest, test } from '@jest/globals';
import { clearEmailAction, emailActionSnapshot, parseEmailLink, receiveEmailLink } from '../src/auth/emailLinks';
import { redirectSystemPath } from '../src/app/+native-intent';

const origin = 'https://example.com';
const token = 'a'.repeat(43);
afterEach(() => { clearEmailAction(); jest.useRealTimers(); });

test.each(['reset', 'verify'])('accepts only the existing HTTPS %s fallback with fragment token', kind => {
  expect(parseEmailLink(`${origin}/app/${kind}.html#token=${token}`, origin)).toEqual({ kind, token });
});
test.each([
  `http://example.com/app/reset.html#token=${token}`, `https://evil.example/app/reset.html#token=${token}`,
  `${origin}/app/reset.html?token=${token}`, `${origin}/app/other.html#token=${token}`,
  `${origin}/app/reset.html#token=${token}&token=${token}`, `${origin}/app/reset.html#token=bad`,
  `https://user:password@example.com/app/reset.html#token=${token}`,
])('rejects untrusted or malformed links', path => { expect(parseEmailLink(path, origin)).toBeNull(); });
test('keeps action only in memory with bounded lifetime and discards it on clear', () => {
  jest.useFakeTimers();
  expect(receiveEmailLink(`${origin}/app/reset.html#token=${token}`, origin)).toBe(true);
  expect(emailActionSnapshot()?.token).toBe(token);
  jest.advanceTimersByTime(30 * 60_000);
  expect(emailActionSnapshot()).toBeNull();
});
test('never returns a secret URL as a navigation path on cold or warm launch', () => {
  for (const initial of [true, false]) {
    const path = redirectSystemPath({ path: `${origin}/app/reset.html#token=${token}`, initial });
    expect(path).toBe('/email-action');
    expect(path).not.toContain(token);
    expect(redirectSystemPath({ path: `/account?token=${token}`, initial })).toBe('/');
  }
});

test('an old in-flight confirmation cannot clear a newer incoming email action', () => {
  jest.useFakeTimers();
  receiveEmailLink(`${origin}/app/reset.html#token=${token}`, origin);
  const first = emailActionSnapshot()!;
  receiveEmailLink(`${origin}/app/verify.html#token=${'b'.repeat(43)}`, origin);
  const second = emailActionSnapshot()!;
  expect(second.id).not.toBe(first.id);
  clearEmailAction(first.id);
  expect(emailActionSnapshot()).toEqual(second);
});
