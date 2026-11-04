import { SocialApiError } from '@/lib/api/social';

const prefix = 'auditgava.social.uploads.v1:';
const uuid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export type UploadRecovery = { identity: string; initiateKey: string; completeKey: string; assetId: string | null; version: number | null; stored: boolean };
type Journal = { version: 1; actor: string; entries: UploadRecovery[] };
function refused() { return new SocialApiError('UPLOAD_RECOVERY_UNAVAILABLE', 'Browser upload recovery is unavailable or full. Keep this tab open and reconcile the original upload before trying again.', [], [], true); }
function valid(entry: UploadRecovery): boolean {
  return !!entry && Object.keys(entry).sort().join(',') === 'assetId,completeKey,identity,initiateKey,stored,version'
    && typeof entry.identity === 'string' && !!entry.identity && entry.identity.length <= 10000
    && typeof entry.initiateKey === 'string' && uuid.test(entry.initiateKey)
    && typeof entry.completeKey === 'string' && uuid.test(entry.completeKey)
    && typeof entry.stored === 'boolean'
    && (entry.assetId === null && entry.version === null && !entry.stored
      || typeof entry.assetId === 'string' && uuid.test(entry.assetId) && Number.isSafeInteger(entry.version) && entry.version! > 0);
}
function read(actor: string): Journal {
  try {
    if (typeof actor !== 'string' || !uuid.test(actor)) throw refused();
    const raw = sessionStorage.getItem(prefix + actor);
    if (raw === null) return { version: 1, actor, entries: [] };
    if (raw.length > 1024 * 1024) throw refused();
    const journal = JSON.parse(raw);
    if (!journal || Object.keys(journal).sort().join(',') !== 'actor,entries,version' || journal.version !== 1 || journal.actor !== actor || !Array.isArray(journal.entries) || journal.entries.length > 100) throw refused();
    const seen = new Set<string>();
    for (const entry of journal.entries) {
      if (!valid(entry) || seen.has(entry.identity)) throw refused();
      seen.add(entry.identity);
    }
    return journal;
  } catch { throw refused(); }
}
function write(journal: Journal) {
  const raw = JSON.stringify(journal);
  if (journal.entries.length > 100 || raw.length > 1024 * 1024 || journal.entries.some(entry => !valid(entry))) throw refused();
  try {
    sessionStorage.setItem(prefix + journal.actor, raw);
    if (sessionStorage.getItem(prefix + journal.actor) !== raw) throw refused();
  } catch { throw refused(); }
}
/** Only identities and progress survive a reload. File bytes and signed grants
 * never enter browser storage. Recovery requires reselecting the exact file.
 */
export function recoverUpload(actor: string, identity: string): UploadRecovery {
  if (typeof identity !== 'string' || !identity || identity.length > 10000) throw refused();
  const journal = read(actor), existing = journal.entries.find(entry => entry.identity === identity);
  if (existing) return existing;
  const entry: UploadRecovery = { identity, initiateKey: crypto.randomUUID(), completeKey: crypto.randomUUID(), assetId: null, version: null, stored: false };
  journal.entries.push(entry); write(journal);
  return entry;
}
export function retainUpload(actor: string, entry: UploadRecovery) {
  if (!valid(entry)) throw refused();
  const journal = read(actor), index = journal.entries.findIndex(item => item.identity === entry.identity && item.initiateKey === entry.initiateKey && item.completeKey === entry.completeKey);
  if (index < 0) throw refused();
  journal.entries[index] = entry; write(journal);
}
export function confirmUpload(actor: string, entry: UploadRecovery) {
  if (!valid(entry)) throw refused();
  const journal = read(actor);
  journal.entries = journal.entries.filter(item => item.identity !== entry.identity || item.initiateKey !== entry.initiateKey || item.completeKey !== entry.completeKey);
  write(journal);
}
