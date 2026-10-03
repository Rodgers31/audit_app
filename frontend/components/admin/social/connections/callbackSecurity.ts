/** Reject messages from other origins, windows and OAuth attempts. */
export function receiveMetaCallback(event: Pick<MessageEvent, 'origin' | 'source' | 'data'>, origin: string, popup: Window | null, state: string | null): { code: string | null; denied: boolean } | null {
  if (!popup || !state || event.origin !== origin || event.source !== popup) return null;
  const v = event.data;
  if (!v || typeof v !== 'object' || Array.isArray(v) || v.type !== 'auditgava-meta-callback' || v.state !== state || typeof v.denied !== 'boolean' || Object.keys(v).some(k => !['type','code','state','denied'].includes(k))) return null;
  if (!v.denied && (typeof v.code !== 'string' || !v.code.length || v.code.length > 4096)) return null;
  return { code: v.denied ? null : v.code, denied: v.denied };
}
