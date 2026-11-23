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

function publicLink(value?: string) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

export const PUBLIC_LINKS = {
  terms: publicLink(process.env.EXPO_PUBLIC_TERMS_URL),
  privacy: publicLink(process.env.EXPO_PUBLIC_PRIVACY_URL),
  support: publicLink(process.env.EXPO_PUBLIC_SUPPORT_URL),
};
