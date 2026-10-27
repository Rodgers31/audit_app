import { NextResponse } from 'next/server';
export const RECOVERY_COOKIE = 'auditgava-recovery';
export const RECOVERY_PATH = '/api/auth/reset-password';
export const MAX_RECOVERY_CODE = 1024;
export const MAX_PASSWORD_BYTES = 1024;
export const MAX_RECOVERY_COOKIE_BYTES = 3800;
const RECOVERY_LIFETIME_MS = 300000;
const SESSION_COOKIE_TAIL = /-auth-token(\.\d+)?$/;
type CookieValue = { name: string; value: string };
export type RecoveryState = {
  version: 1;
  flow: string;
  code: string;
  expiresAt: number;
  verifier: CookieValue[];
};
export function validRecoveryCode(code: unknown): code is string {
  return typeof code === 'string' && code.length > 0 && code.length <= MAX_RECOVERY_CODE &&
    /^[\x21-\x7e]+$/.test(code);
}
export function isResetPasswordPath(pathname: string): boolean {
  return pathname.replace(/\/+$/, '') === '/reset-password';
}
export function privateResponse(response: NextResponse) {
  response.headers.set('Cache-Control', 'private, no-store');
  response.headers.set('Referrer-Policy', 'no-referrer');
  return response;
}
function recoveryVerifier(cookies: CookieValue[]): CookieValue[] | null {
  let base: string;
  try {
    const project = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL!).hostname.split('.')[0];
    if (!project || !/^[a-zA-Z0-9-]+$/.test(project)) return null;
    base = `sb-${project}-auth-token-code-verifier`;
  } catch { return null; }
  const selected = cookies.filter(c => c.name === base || c.name.startsWith(base + '.'));
  if (selected.length === 0 || selected.length > 4 ||
    new Set(selected.map(c => c.name)).size !== selected.length ||
    selected.some(c => typeof c.value !== 'string' || c.value.length === 0 ||
      c.value.length > 1024 || !/^[\x21-\x7e]+$/.test(c.value))) return null;
  if (selected.some(c => c.name === base)) {
    return selected.length === 1 ? selected.map(c => ({ name: c.name, value: c.value })) : null;
  }
  selected.sort((a, b) => a.name.localeCompare(b.name));
  if (selected.some((c, index) => c.name !== `${base}.${index}`)) return null;
  return selected.map(c => ({ name: c.name, value: c.value }));
}
export function readRecovery(value: unknown): RecoveryState | null {
  try {
    if (typeof value !== 'string' || value.length > MAX_RECOVERY_COOKIE_BYTES ||
      encodeURIComponent(value).length > MAX_RECOVERY_COOKIE_BYTES) return null;
    const state = JSON.parse(value);
    const now = Date.now();
    if (!state || typeof state !== 'object' || Array.isArray(state) ||
      state.version !== 1 || typeof state.flow !== 'string' || !/^[a-f0-9]{32}$/.test(state.flow) ||
      !validRecoveryCode(state.code) || !Number.isSafeInteger(state.expiresAt) ||
      state.expiresAt <= now || state.expiresAt > now + RECOVERY_LIFETIME_MS ||
      !Array.isArray(state.verifier) || state.verifier.length > 4 ||
      state.verifier.some((c: CookieValue) => !c || typeof c.name !== 'string')) return null;
    const verifier = recoveryVerifier(state.verifier);
    return verifier && verifier.length === state.verifier.length ? { version: 1, flow: state.flow, code: state.code, expiresAt: state.expiresAt, verifier } : null;
  } catch { return null; }
}
export function recoveryRedirect(requestUrl: string, code: string | null, cookies: CookieValue[]) {
  const url = new URL('/reset-password', requestUrl);
  const verifier = recoveryVerifier(cookies);
  let state: RecoveryState | null = null;
  if (validRecoveryCode(code) && verifier) {
    const random = crypto.getRandomValues(new Uint8Array(16));
    const candidate: RecoveryState = {
      version: 1, flow: Array.from(random, v => v.toString(16).padStart(2, '0')).join(''),
      code, verifier, expiresAt: Date.now() + RECOVERY_LIFETIME_MS,
    };
    if (encodeURIComponent(JSON.stringify(candidate)).length <= MAX_RECOVERY_COOKIE_BYTES) state = candidate;
  }
  if (state) url.hash = new URLSearchParams({ 'recovery-flow': state.flow }).toString();
  else url.searchParams.set('error', 'Invalid reset link. Please request a new one.');
  const response = privateResponse(NextResponse.redirect(url));
  if (state) {
    response.cookies.set(RECOVERY_COOKIE, JSON.stringify(state), {
      httpOnly: true, secure: true, sameSite: 'lax',
      path: RECOVERY_PATH, maxAge: RECOVERY_LIFETIME_MS / 1000,
    });
    for (const { name } of cookies) {
      if (name.startsWith('sb-') && SESSION_COOKIE_TAIL.test(name)) {
        response.cookies.set(name, '', { maxAge: 0, path: '/', sameSite: 'lax', secure: true });
      }
    }
  }
  // Invalid links cannot clear a newer tab's staged code or authenticated session.
  return response;
}
