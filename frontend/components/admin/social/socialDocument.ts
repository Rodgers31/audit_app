import { DocumentTarget, SocialAccount, SocialContent, SocialDocument, SocialDraftInput, SocialPlatform } from '@/lib/api/social';

export const platformLabels: Record<SocialPlatform, string> = { facebook: 'Facebook', instagram: 'Instagram', threads: 'Threads', x: 'X', tiktok: 'TikTok' };
export const emptyDocument = (): SocialDocument => ({ schema_version: 1, master: { text: '', link: null, hashtags: [], media: [] }, targets: [] });
/** Response correlation preserves exactly what the admin submitted, including empty overrides. */
export function draftFingerprint(draft: SocialDraftInput): string {
  const normalizedMedia = (value: SocialContent['media']) => value.map(a => ({ ...a, alt_text: a.alt_text ?? null }));
  const normalized = {
    title: draft.title, content_type: draft.content_type,
    document: { ...draft.document, master: { ...draft.document.master, media: normalizedMedia(draft.document.master.media) }, targets: draft.document.targets.map(t => ({ ...t, overrides: { ...t.overrides, ...(t.overrides.media ? { media: { mode: 'replace', value: normalizedMedia(t.overrides.media.value) } } : {}) } })) },
    references: draft.references.map(r => ({ ...r, label: r.label ?? null })),
  };
  const sorted = (value: unknown): unknown => Array.isArray(value) ? value.map(sorted) : value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, sorted(item)])) : value;
  return JSON.stringify(sorted(normalized));
}
export function resolveContent(master: SocialContent, target?: DocumentTarget): SocialContent {
  return {
    text: target?.overrides.text?.value ?? master.text,
    link: target?.overrides.link ? target.overrides.link.value : master.link,
    hashtags: target?.overrides.hashtags?.value ?? master.hashtags,
    media: target?.overrides.media?.value ?? master.media,
  };
}
export function supportedFormats(account: SocialAccount | undefined): string[] {
  const value = account?.capabilities.supported_formats;
  return Array.isArray(value) ? value : [];
}
export function targetHints(master: SocialContent, target: DocumentTarget, account?: SocialAccount): string[] {
  if (!account) return ['Account is unavailable. Explicitly remove it or refresh the connected accounts.'];
  const hints: string[] = [];
  if (!account.publishing_enabled) hints.push('Publishing is disabled for this account.');
  const formats = supportedFormats(account);
  if (!formats.length) hints.push('Supported formats are unknown. Backend validation is required.');
  else if (!formats.includes(target.format)) hints.push(`This account does not support the ${target.format} format.`);
  const content = resolveContent(master, target);
  if (target.format !== 'text' && !content.media.length) hints.push('This format needs media. Uploads are unavailable in this batch.');
  if (target.format === 'text' && content.media.length) hints.push('Media references are selected with a text format. Check backend validation.');
  if (!account.capabilities.eligible) hints.push('Publishing eligibility has not been verified.');
  if (!account.capabilities.adapter_available) hints.push('This platform adapter is unavailable.');
  if (account.capabilities.price_class === 'paid') hints.push('This account requires paid API access. Confirm the approved budget before publication.');
  const limit = account.capabilities.limits.max_text_length;
  if (typeof limit === 'number' && Number.isFinite(limit) && limit >= 0 && Array.from(content.text).length > limit) hints.push(`Text exceeds the reported ${limit} character limit. Counting here is provisional.`);
  return hints;
}
export function httpsUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : undefined; } catch { return undefined; }
}

export interface CivilCandidate { utc: string; offset: string }
/** Resolve the selected future civil time in its IANA zone, including DST gaps/folds. */
export function resolveCivilTime(localTime: string, timezone: string): { candidates: CivilCandidate[]; error?: string } {
  if (!localTime) return { candidates: [] };
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(localTime);
  if (!match) return { candidates: [], error: 'Enter a valid local date and time.' };
  const [, year, month, day, hour, minute, seconds = '00'] = match;
  const civil = `${year}-${month}-${day}T${hour}:${minute}:${seconds}`;
  const base = Date.parse(`${civil}Z`);
  if (!Number.isFinite(base) || new Date(base).toISOString().slice(0, 19) !== civil) return { candidates: [], error: 'Enter a valid local date and time.' };
  try {
    const formatter = new Intl.DateTimeFormat('en-GB', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
    const candidates: CivilCandidate[] = [];
    for (let offset = -14 * 60; offset <= 14 * 60; offset += 15) {
      const instant = base - offset * 60_000;
      const parts = Object.fromEntries(formatter.formatToParts(instant).map(p => [p.type, p.value]));
      if (`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}` === civil) {
        const sign = offset < 0 ? '-' : '+';
        candidates.push({ utc: new Date(instant).toISOString(), offset: `${sign}${String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0')}:${String(Math.abs(offset) % 60).padStart(2, '0')}` });
      }
    }
    return candidates.length ? { candidates } : { candidates, error: 'This local time does not exist in the selected timezone. Choose another time.' };
  } catch { return { candidates: [], error: 'Enter a recognized IANA timezone, such as Africa/Nairobi.' }; }
}
