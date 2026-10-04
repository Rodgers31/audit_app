/** Standalone callback response excludes the app shell, analytics and external scripts. */
import { createHash } from 'node:crypto';
export const dynamic = 'force-dynamic';
const script = `(() => {
  const query = new URLSearchParams(window.location.search);
  window.history.replaceState(null, '', window.location.pathname);
  const code = query.get('code'), state = query.get('state');
  const message = { type: 'auditgava-meta-callback', code, state, denied: query.has('error') };
  query.delete('code'); query.delete('state');
  if (window.opener) {
    window.opener.postMessage(message, window.location.origin);
    document.getElementById('message').textContent = 'Return to the admin window to confirm the exact accounts.';
    window.close();
  }
})();`;
export function GET() {
  const hash = createHash('sha256').update(script).digest('base64');
  return new Response(`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AuditGava account connection</title><p id="message">Return to the admin Accounts page and start a new connection if the original window is closed.</p><script>${script}</script></html>`, { headers: {
    'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': `default-src 'none'; script-src 'sha256-${hash}'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
    'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
  } });
}
