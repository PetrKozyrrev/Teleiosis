export function redirectSystemPath({ path }: { path: string; initial: boolean }) {
  if (path.startsWith('/') && !path.startsWith('//')) return path;
  try {
    if (new URL(path).hostname === 'expo-sharing') return '/share-probe';
    return path;
  } catch {
    return '/';
  }
}
