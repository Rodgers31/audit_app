/** Only an expiring flow reference is retained. Grants, codes and state stay out of storage. */
const key = 'auditgava.meta.connection-recovery.v1';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type Reference = { version: 1; actor: string; flow: string; expires: string };

function valid(value: unknown, actor: string | undefined): value is Reference {
  if (typeof actor !== 'string' || !actor || actor.length > 128 || actor.trim() !== actor || !value || typeof value !== 'object' || Array.isArray(value)) return false;
  const v = value as Record<string, unknown>;
  if (Object.keys(v).length !== 4 || v.version !== 1 || v.actor !== actor || typeof v.flow !== 'string' || !uuid.test(v.flow) || typeof v.expires !== 'string' || v.expires.length > 64) return false;
  const remaining = Date.parse(v.expires) - Date.now();
  // Server flows last ten minutes. Allow clock skew, never an unbounded reference.
  return Number.isFinite(remaining) && remaining > 0 && remaining <= 15 * 60_000;
}

export function readConnectionRecovery(actor: string | undefined): { flow: string | undefined; available: boolean } {
  if (!actor) return { flow: undefined, available: true };
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return { flow: undefined, available: true };
    const value: unknown = JSON.parse(raw);
    if (value && typeof value === 'object' && 'actor' in value && typeof value.actor === 'string' && valid(value, value.actor)) return { flow: value.actor === actor ? value.flow : undefined, available: true };
    window.sessionStorage.removeItem(key);
    return { flow: undefined, available: true };
  } catch {
    return { flow: undefined, available: false };
  }
}

export function saveConnectionRecovery(actor: string, flow: string, expires: string): boolean {
  const value = { version: 1, actor, flow, expires };
  if (!valid(value, actor)) return false;
  try { window.sessionStorage.setItem(key, JSON.stringify(value)); return true; }
  catch { return false; }
}

export function forgetConnectionRecovery(actor: string, flow: string): boolean {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return true;
    const value: unknown = JSON.parse(raw);
    if (value && typeof value === 'object' && !Array.isArray(value) && 'actor' in value && 'flow' in value && value.actor === actor && value.flow === flow) window.sessionStorage.removeItem(key);
    return true;
  } catch { return false; }
}
