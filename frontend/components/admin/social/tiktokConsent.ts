import type { DocumentTarget, SocialDocument, SocialDraftInput } from '@/lib/api/social';
import { resolveContent } from './socialDocument';

const confirmations = new Set(['upload_consent', 'music_usage_confirmed', 'branded_content_policy_confirmed']);
function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, ordered(item)]));
  return value;
}
function reviewedContent(document: SocialDocument, target: DocumentTarget): string {
  const content = resolveContent(document.master, target);
  return JSON.stringify(ordered({
    account_id: target.account_id,
    format: target.format,
    content: { ...content, media: content.media.map(asset => ({ ...asset, alt_text: asset.alt_text ?? null })) },
    options: Object.fromEntries(Object.entries(target.tiktok_options ?? {}).filter(([key]) => !confirmations.has(key))),
  }));
}

/** Confirmation describes one account's effective publication, not internal draft metadata. */
export function clearChangedTikTokConfirmations(previous: SocialDraftInput, next: SocialDraftInput): SocialDraftInput {
  let changed = false;
  const targets = next.document.targets.map(target => {
    if (!target.tiktok_options) return target;
    const before = previous.document.targets.find(item => item.account_id === target.account_id);
    if (before?.tiktok_options && reviewedContent(previous.document, before) === reviewedContent(next.document, target)) return target;
    changed = true;
    return { ...target, tiktok_options: { ...target.tiktok_options, upload_consent: false, music_usage_confirmed: false, branded_content_policy_confirmed: false } };
  });
  return changed ? { ...next, document: { ...next.document, targets } } : next;
}
