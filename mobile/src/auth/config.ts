export function apiOrigin(value: string | undefined): string | null {
  if (!value) return null;
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('API origin must be HTTPS without credentials, path or parameters');
  }
  return url.origin;
}

export const API_ORIGIN = apiOrigin(process.env.EXPO_PUBLIC_API_ORIGIN);
export const STAGING_GATE = process.env.EXPO_PUBLIC_STAGING_GATE === '1';
