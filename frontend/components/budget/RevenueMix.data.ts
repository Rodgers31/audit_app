import { evidenceUrl, type Qualifications } from '@/lib/evidence/qualification';

export interface RevSource {
  qualifications?: Qualifications;
  revenue_type: string;
  category?: string | null;
  amount?: number | null; // KES billions
  yoy_growth_pct?: number | null;
  basis?: string | null;
  basis_note?: string | null;
  absent_reason?: string | null;
  source_absent_reason?: string | null;
  measure?: string | null;
  source?: {
    url?: string;
    data_url?: string;
    version?: string;
    period?: string;
    retrieved_at?: string | null;
    publication_date?: string | null;
    reconciliation?: string;
    stated_amount_billion_kes?: string;
  } | null;
}

export interface RevFy {
  fiscal_year: string;
  sources: RevSource[];
}

export function fiscalStart(label: string) {
  const match = /^(?:FY\s*)?(\d{4})\s*[/-]\s*(\d{2}|\d{4})$/i.exec(label.trim());
  if (!match) return null;
  const start = Number(match[1]);
  return (start + 1) % (10 ** match[2].length) === Number(match[2]) ? start : null;
}

export const isTotal = (row: RevSource) => row.category === 'total' || /^total /i.test(row.revenue_type);
export const withheldResidual = (row: RevSource) => row.revenue_type === 'Other Tax Revenue' && row.basis !== 'published';
export const hasAmount = (row: RevSource): row is RevSource & { amount: number } =>
  typeof row.amount === 'number' && Number.isFinite(row.amount) && row.amount >= 0 &&
  !row.absent_reason && !withheldResidual(row);

function growthFor(row: RevSource & { amount: number }, previous?: RevFy) {
  if (row.basis !== 'published') return null;
  if (typeof row.yoy_growth_pct === 'number' && Number.isFinite(row.yoy_growth_pct)) {
    return { amount: row.yoy_growth_pct, basis: 'published' as const };
  }
  const prior = previous?.sources.find(previousRow => previousRow.revenue_type === row.revenue_type);
  if (!prior || !hasAmount(prior) || prior.basis !== 'published' || prior.amount <= 0 ||
      (prior.measure || prior.revenue_type) !== (row.measure || row.revenue_type) ||
      (prior.category && row.category && prior.category !== row.category)) return null;
  return { amount: (row.amount / prior.amount - 1) * 100, basis: 'calculated' as const };
}

export function revenueRanking(revenueBySource: RevFy[]) {
  const releases = revenueBySource.map(release => ({ ...release, start: fiscalStart(release.fiscal_year) }))
    .sort((left, right) => (left.start ?? -Infinity) - (right.start ?? -Infinity));
  const latest = releases.findLast(release => release.sources.some(row => hasAmount(row) && row.basis !== 'projected'));
  if (!latest) return null;
  const previous = releases.find(release => latest.start != null && release.start === latest.start - 1);
  const ranked = latest.sources.filter(hasAmount)
    .filter(row => !isTotal(row) && row.basis !== 'projected')
    .sort((left, right) => right.amount - left.amount)
    .map(row => ({ ...row, growth: growthFor(row, previous) }));
  return { latest, ranked, releases };
}

export function sourceLocator(source: RevSource['source']) {
  return evidenceUrl(source?.data_url) ?? evidenceUrl(source?.url);
}

export function revenuePublisher(row: RevSource) {
  const names = new Set(Object.values(row.qualifications ?? {}).flatMap(qualification => {
    const name = qualification?.publisher?.trim();
    return name ? [name === 'Kenya Revenue Authority' ? 'KRA' : name] : [];
  }));
  if (names.size === 1) return Array.from(names)[0];
  const publisherUrl = evidenceUrl(row.source?.url);
  return names.size === 0 && publisherUrl &&
    /(^|\.)kra\.go\.ke$/i.test(new URL(publisherUrl).hostname) ? 'KRA' : null;
}

export function compactRevenue(amount: number) {
  if (amount >= 1000) return `KES ${(amount / 1000).toFixed(2)}T`;
  if (amount > 0 && amount < 1) return `KES ${Math.round(amount * 1e9).toLocaleString('en-KE')}`;
  return `KES ${amount.toFixed(0)}B`;
}
