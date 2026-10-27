import { NextResponse } from 'next/server';
export const RECOVERY_COOKIE = 'auditgava-recovery';
export const RECOVERY_PATH = '/api/auth/reset-password';
export const MAX_RECOVERY_CODE = 1024;
export const MAX_PASSWORD_BYTES = 1024;
const SESSION_COOKIE_TAIL = /-auth-token(\.\d+)?$/;
export function validRecoveryCode(code: unknown): code is string {
  return typeof code === 'string' && code.length > 0 && code.length <= MAX_RECOVERY_CODE &&
    /^[\x21-\x7e]+$/.test(code);
}
export function privateResponse(response: NextResponse) {
  response.headers.set('Cache-Control', 'private, no-store');
  response.headers.set('Referrer-Policy', 'no-referrer');
  return response;
}
export function clearRecovery(response: NextResponse) {
  response.cookies.set(RECOVERY_COOKIE, '', {
    httpOnly: true, secure: true, sameSite: 'lax',
    path: RECOVERY_PATH, maxAge: 0,
  });
  return response;
}
export function recoveryRedirect(requestUrl: string, code: string | null, cookies: {
  name: string;
}[]) {
  const url = new URL('/reset-password', requestUrl);
  if (!validRecoveryCode(code))
    url.searchParams.set('error', 'Invalid reset link. Please request a new one.');
  const response = privateResponse(NextResponse.redirect(url));
  if (validRecoveryCode(code)) {
    response.cookies.set(RECOVERY_COOKIE, code, {
      httpOnly: true, secure: true, sameSite: 'lax',
      path: RECOVERY_PATH, maxAge: 300,
    });
  }
  else {
    clearRecovery(response);
  }
  for (const { name } of cookies) {
    if (name.startsWith('sb-') && SESSION_COOKIE_TAIL.test(name)) {
      response.cookies.set(name, '', { maxAge: 0, path: '/', sameSite: 'lax', secure: true });
    }
  }
  return response;
}
