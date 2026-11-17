import { API_ORIGIN } from '../auth/config';
import { receiveEmailLink } from '../auth/emailLinks';

export function redirectSystemPath({ path }: { path: string; initial: boolean }) {
  try {
    if (new URL(path).hostname === 'expo-sharing') return '/share-probe';
  } catch { /* Internal relative routes are also valid. */ }
  if (/^https?:\/\//i.test(path) || path.startsWith('/app/reset.html') || path.startsWith('/app/verify.html')) {
    receiveEmailLink(path, API_ORIGIN);
    return '/email-action';
  }
  // Never put unknown query/fragment values into navigation state or history.
  if (path.includes('?') || path.includes('#')) return '/';
  if (path.startsWith('/') && !path.startsWith('//')) return path;
  return '/';
}
