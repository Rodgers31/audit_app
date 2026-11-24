import type { UnaccountedCase } from '@/types';

const romanVolumes: Record<string, string> = { I: '1', II: '2', III: '3', IV: '4', V: '5' };

type ReportScope = 'countyExecutives' | 'countyAssemblies' | 'countyGovernments' | 'nationalGovernment';

function sourceScope(title: string): ReportScope | null {
  const executives = /\b(?:county|green book) executives\b/i.test(title);
  const assemblies = /\b(?:county|green book) assemb(?:lies|les)\b/i.test(title);
  if (executives && !assemblies) return 'countyExecutives';
  if (assemblies && !executives) return 'countyAssemblies';
  if ((executives && assemblies) || /\bcounty governments?\b/i.test(title)) return 'countyGovernments';
  if (/\bnational government\b/i.test(title)) return 'nationalGovernment';
  return null;
}

/** Scope and volume are explicit report metadata. A numeric filename suffix is not a volume. */
export function reportCitationParts(source: UnaccountedCase['source']) {
  const publisher = source.publisher?.trim() || null;
  const office = publisher && /^(oag|office of the auditor[- ]general)$/i.test(publisher);
  const title = (source.title ?? '').replace(/[-_.]+/g, ' ');
  const volume = /\bvol(?:ume)?\s+([1-9]\d?|[iv]+)\b/i.exec(title)?.[1]?.toUpperCase();

  return {
    publisher: office ? 'OAG' : publisher,
    scope: office ? sourceScope(title) : null,
    volume: office && volume ? romanVolumes[volume] ?? volume : null,
  };
}

export function reportPageHref(finding: UnaccountedCase) {
  if (!finding.source.page_url || !finding.page_ref?.trim()) return null;

  try {
    const url = new URL(finding.source.page_url);
    return url.protocol === 'https:' || url.protocol === 'http:' ? finding.source.page_url : null;
  } catch {
    return null;
  }
}
