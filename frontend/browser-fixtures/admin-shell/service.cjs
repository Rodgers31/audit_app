// Inert loopback auth transport for the REAL app middleware and AuthProvider.
// No product aliases, seeded database, upstream proxy, or live credentials.
const { createServer } = require('node:http');

const port = 8137;
const actor = '00000000-0000-4000-8000-000000000001';
function session(role = 'admin') {
  const payload = { sub: actor, aud: 'authenticated', role: 'authenticated', exp: Math.floor(Date.now() / 1000) + 3600, app_metadata: { fixture_role: role } };
  const token = `${Buffer.from('{"alg":"HS256","typ":"JWT"}').toString('base64url')}.${Buffer.from(JSON.stringify(payload)).toString('base64url')}.inert-local-signature`;
  return { access_token: token, refresh_token: 'inert-local-refresh', expires_at: payload.exp, expires_in: 3600, token_type: 'bearer', user: user(role) };
}
function user(role) {
  return { id: actor, aud: 'authenticated', role: 'authenticated', email: 'shell@example.invalid', app_metadata: { fixture_role: role }, user_metadata: {}, created_at: '2026-01-01T00:00:00Z' };
}
function roleOf(req) {
  try { return JSON.parse(Buffer.from((req.headers.authorization || '').split('.')[1], 'base64url')).app_metadata.fixture_role; } catch { return null; }
}
function startService() {
  const server = createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', 'http://127.0.0.1:3137');
    res.setHeader('Access-Control-Allow-Headers', 'authorization, apikey, content-type, x-client-info, x-supabase-api-version');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json');
    const send = (status, body) => { res.statusCode = status; res.end(JSON.stringify(body)); };
    if (req.method === 'OPTIONS') return send(200, {});
    if (req.url === '/health') return send(200, { fixture: 'admin-shell', writes: 'off' });
    const role = roleOf(req);
    if (req.method === 'GET' && req.url?.startsWith('/auth/v1/user')) return role ? send(200, user(role)) : send(401, { message: 'No fixture session' });
    if (req.method === 'GET' && req.url?.startsWith('/rest/v1/profiles')) return send(200, { id: actor, email: 'shell@example.invalid', display_name: 'Local reviewer', roles: role === 'admin' ? ['admin'] : ['editor'] });
    if (req.method === 'POST' && req.url?.startsWith('/auth/v1/logout')) return send(204, null);
    // Unlisted reads and EVERY product write refuse, including public SSR fetches.
    return send(req.method === 'GET' ? 503 : 403, { detail: 'Inert shell fixture: unavailable' });
  });
  return server.listen(port, '127.0.0.1');
}
module.exports = { port, actor, session, startService };
if (require.main === module) startService();
