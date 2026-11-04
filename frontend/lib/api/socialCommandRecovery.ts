import { SocialApiError } from './social';

const prefix = 'auditgava.social.commands.v1:';
const uuid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const maximum = 2 * 1024 * 1024;
type Journal = { version: 1; actor: string; entries: { identity: string; key: string }[] };

function refused() {
  return new SocialApiError('COMMAND_RECOVERY_UNAVAILABLE', 'Browser command recovery is unavailable or full. Keep this tab open and reconcile the original command before trying again.');
}
function storageKey(actor: string | undefined) {
  if (typeof actor !== 'string' || !uuid.test(actor)) throw refused();
  return prefix + actor;
}
function read(actor: string | undefined): Journal {
  const key = storageKey(actor);
  try {
    const raw = sessionStorage.getItem(key);
    if (raw === null) return { version: 1, actor: actor!, entries: [] };
    if (raw.length > maximum) throw refused();
    const value = JSON.parse(raw);
    if (!value || Object.keys(value).sort().join(',') !== 'actor,entries,version' || value.version !== 1 || value.actor !== actor || !Array.isArray(value.entries) || value.entries.length > 100) throw refused();
    const seen = new Set<string>();
    for (const entry of value.entries) {
      if (!entry || Object.keys(entry).sort().join(',') !== 'identity,key' || typeof entry.identity !== 'string' || !entry.identity || entry.identity.length > maximum || typeof entry.key !== 'string' || !uuid.test(entry.key) || seen.has(entry.identity)) throw refused();
      seen.add(entry.identity);
    }
    return value;
  } catch { throw refused(); }
}
function write(journal: Journal) {
  const key = storageKey(journal.actor), raw = JSON.stringify(journal);
  if (journal.entries.length > 100 || raw.length > maximum) throw refused();
  try {
    sessionStorage.setItem(key, raw);
    if (sessionStorage.getItem(key) !== raw) throw refused();
  } catch { throw refused(); }
}

/** Tab-scoped recovery survives navigation/reload. It never triggers a retry.
 * Exact draft intents remain private to this actor's tab; never pass credentials
 * or signed media grants here. Unconfirmed entries have no automatic expiry.
 */
export function socialCommandKey(actor: string | undefined, identity: string): string {
  if (typeof identity !== 'string' || !identity || identity.length > maximum) throw refused();
  const journal = read(actor), existing = journal.entries.find(entry => entry.identity === identity);
  if (existing) return existing.key;
  const key = crypto.randomUUID();
  if (!uuid.test(key)) throw refused();
  journal.entries.push({ identity, key }); write(journal);
  return key;
}
export function confirmSocialCommand(actor: string | undefined, identity: string, key: string) {
  if (typeof identity !== 'string' || !identity || identity.length > maximum || typeof key !== 'string' || !uuid.test(key)) throw refused();
  const journal = read(actor);
  // A late result cannot retire another command's recovery reference.
  journal.entries = journal.entries.filter(entry => entry.identity !== identity || entry.key !== key);
  write(journal);
}

/** The original bytes distinguish same-name/size/timestamp files. No file bytes,
 * alt text or grants are retained by this digest helper.
 */
export async function mediaFileDigest(file: File): Promise<string> {
  try {
    const bytes = await new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('media read failed')); reader.onabort = () => reject(new Error('media read failed'));
      reader.onload = () => reader.result instanceof ArrayBuffer ? resolve(reader.result) : reject(new Error('media read failed'));
      reader.readAsArrayBuffer(file);
    });
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  } catch { throw new SocialApiError('MEDIA_FILE_READ_FAILED', 'This media file could not be read securely. Reselect the original file and retry. No upload was started.', [], [], true); }
}

export function socialCommandIdentity(actor: string | undefined, method: 'post' | 'patch', path: string, body: object): string {
  return JSON.stringify([actor, method, path, body]);
}

/** Direct command callers use the same durable contract as useSocialMutation.
 * The callback must bind its response to the submitted route/body and known
 * resource/version before resolving; schema-only decoding is not confirmation. Never pass OAuth
 * codes, credentials, launch tokens or signed grants into this journal.
 */
export async function recoveredSocialCommand<T>(actor: string | undefined, method: 'post' | 'patch', path: string, body: object, execute: (key: string) => Promise<T>, current: () => boolean = () => true): Promise<T> {
  if (!current()) throw new SocialApiError('ACCESS_DENIED', 'The admin session or editor changed. Review this action again.');
  const identity = socialCommandIdentity(actor, method, path, body), key = socialCommandKey(actor, identity);
  if (!current()) throw new SocialApiError('ACCESS_DENIED', 'The admin session or editor changed. Review this action again.');
  const result = await execute(key);
  if (current()) confirmSocialCommand(actor, identity, key);
  return result;
}

/** New rule IDs are generated by the UI. On an explicit identical retry after
 * reload, retain the original path as well as the original body and key.
 * This narrow rule-create case does not equate changed timestamps or bodies.
 */
export function recoverGeneratedRulePath(actor: string | undefined, method: 'post' | 'patch', path: string, body: object): string {
  const rulePath = /^\/automation\/rules\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\/versions$/i;
  if (method !== 'post' || !rulePath.test(path) || !('expected_version' in body) || body.expected_version !== 0) return path;
  const matches: string[] = [];
  for (const entry of read(actor).entries) {
    let value: unknown; try { value = JSON.parse(entry.identity); } catch { continue; }
    if (!Array.isArray(value) || value.length !== 4) continue;
    const [owner, verb, retainedPath, retainedBody] = value;
    if (owner === actor && verb === method && typeof retainedPath === 'string' && rulePath.test(retainedPath) && JSON.stringify(retainedBody) === JSON.stringify(body)) matches.push(retainedPath);
  }
  if (matches.length > 1) throw refused();
  return matches[0] ?? path;
}
