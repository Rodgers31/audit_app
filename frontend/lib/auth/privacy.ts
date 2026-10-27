/** Browser collectors must never receive authentication URLs or query material. */
export function isPrivateAuthPath(pathname: string): boolean {
  return pathname === '/reset-password' || pathname.startsWith('/reset-password/') ||
    pathname === '/auth' || pathname.startsWith('/auth/') ||
    pathname === '/api/auth' || pathname.startsWith('/api/auth/') ||
    pathname.startsWith('/admin/social/accounts/callback') ||
    pathname.startsWith('/admin/social/accounts/platform-callback');
}
export function isPrivateAuthUrl(value: string): boolean {
  try {
    const url = new URL(value, 'https://app.invalid');
    if (isPrivateAuthPath(url.pathname))
      return true;
    return Array.from(url.searchParams.keys()).some(key => /^(code|recovery|state|.*token.*|error_description)$/i.test(key)) ||
      /(?:access_token|refresh_token|recovery|code)=/i.test(url.hash);
  }
  catch {
    return true;
  }
}
// Also applies to a collector loaded on a previous public SPA page. Checking
// both URLs blocks delayed events and a public event during private navigation.
export function filterAuthEvent<T extends {
  url: string;
}>(event: T): T | null {
  if (isPrivateAuthUrl(event.url) ||
    (typeof window !== 'undefined' && isPrivateAuthUrl(window.location.href)))
    return null;
  return event;
}
