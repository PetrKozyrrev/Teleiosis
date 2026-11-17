import { describe, expect, test } from '@jest/globals';
import { inspectShare, MAX_PROBE_TEXT_LENGTH } from '../src/platform/share';
import { redirectSystemPath } from '../src/app/+native-intent';

describe('raw share investigation', () => {
  test('accepts a PDF URL without downloading or treating it as a file', () => {
    expect(inspectShare([{ shareType: 'url', value: ' https://example.com/book.pdf ' }]))
      .toEqual({ ok: true, item: { kind: 'url', value: 'https://example.com/book.pdf' } });
  });
  test('keeps a note with an embedded URL intact', () => {
    const text = 'Изучить\nhttps://example.com/?q=1';
    expect(inspectShare([{ shareType: 'text', value: text }]))
      .toEqual({ ok: true, item: { kind: 'text', value: text } });
  });
  test.each(['javascript:alert(1)', 'file:///private/test', 'https://user:password@example.com/', 'not a url'])('rejects an unsafe URL payload %s', value => {
    expect(inspectShare([{ shareType: 'url', value }]).ok).toBe(false);
  });
  test.each(['', '   ', 'a'.repeat(MAX_PROBE_TEXT_LENGTH + 1)])('rejects empty/oversized text', value => {
    expect(inspectShare([{ shareType: 'text', value }]).ok).toBe(false);
  });
  test('does not silently take one of several payloads or accept file contents', () => {
    expect(inspectShare([]).ok).toBe(false);
    expect(inspectShare([{ shareType: 'file', value: 'content://book.pdf' }]).ok).toBe(false);
    const item = { shareType: 'text' as const, value: 'one' };
    expect(inspectShare([item, item]).ok).toBe(false);
  });
  test('routes sharing without copying content into navigation params', () => {
    expect(redirectSystemPath({ path: 'teleiosis-dev://expo-sharing', initial: true })).toBe('/share-probe');
    expect(redirectSystemPath({ path: 'teleiosis-dev://expo-sharing', initial: false })).toBe('/share-probe');
    expect(redirectSystemPath({ path: '/', initial: false })).toBe('/');
    expect(redirectSystemPath({ path: '/probe', initial: false })).toBe('/probe');
    expect(redirectSystemPath({ path: 'malformed', initial: false })).toBe('/');
  });
});
