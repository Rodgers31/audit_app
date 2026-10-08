/** Validate a base URL without logging its supplied value. */
function validateHttpBaseUrl(value, name) {
  if (typeof value !== 'string' || !value || value !== value.trim() || /\s/.test(value)) {
    throw new Error(`${name} must be an explicit nonblank absolute HTTP(S) URL`);
  }
  if (!/^https?:\/\/[^/\\]/i.test(value) || value.includes('\\')) {
    throw new Error(`${name} must be an absolute HTTP(S) URL`);
  }
  let url;
  try { url = new URL(value); } catch { throw new Error(`${name} must be a valid absolute HTTP(S) URL`); }
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname) {
    throw new Error(`${name} must be an absolute HTTP(S) URL`);
  }
  if (url.username || url.password || /^https?:\/\/[^/?#]*@/i.test(value)) {
    throw new Error(`${name} must not contain embedded credentials`);
  }
  if (value.includes('?') || value.includes('#')) {
    throw new Error(`${name} must not contain a query or fragment`);
  }
  return url.href.replace(/\/+$/, '');
}

function validatePublicConfig(env) {
  const api = validateHttpBaseUrl(env.NEXT_PUBLIC_API_URL, 'NEXT_PUBLIC_API_URL');
  const supabase = validateHttpBaseUrl(env.NEXT_PUBLIC_SUPABASE_URL, 'NEXT_PUBLIC_SUPABASE_URL');
  const anon = env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (typeof anon !== 'string' || !anon || /\s/.test(anon)) {
    throw new Error('NEXT_PUBLIC_SUPABASE_ANON_KEY must be an explicit nonblank public anon key');
  }
  return { NEXT_PUBLIC_API_URL: api, NEXT_PUBLIC_SUPABASE_URL: supabase, NEXT_PUBLIC_SUPABASE_ANON_KEY: anon };
}

module.exports = { validateHttpBaseUrl, validatePublicConfig };
