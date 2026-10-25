import type { TranslationKey } from '@/lib/i18n/messages';

export type BorrowingSource = { url: string; scope: string; pdf_pages: readonly number[] };
export type BorrowingCoverage = {
  status?: string;
  complete_liability_coverage?: false;
  sources?: ReadonlyArray<BorrowingSource>;
};

export function borrowingSources(coverage?: BorrowingCoverage): readonly BorrowingSource[] {
  const sources = coverage?.sources;
  if (!Array.isArray(sources) || sources.length > 8) return [];
  const valid = sources.every(source => {
    if (!source || typeof source !== 'object' || typeof source.scope !== 'string' ||
        !source.scope || source.scope.length > 200 || typeof source.url !== 'string' || source.url.length > 2048 ||
        !Array.isArray(source.pdf_pages) || !source.pdf_pages.length || source.pdf_pages.length > 4 ||
        !source.pdf_pages.every((page: unknown) => typeof page === 'number' && Number.isInteger(page) && page > 0 && page <= 5000)) return false;
    try { const url = new URL(source.url); return url.protocol === 'https:' && !url.username && !url.password; } catch { return false; }
  });
  return valid ? sources : [];
}

function stockDate(value?: string | null): boolean {
  if (typeof value !== 'string' || (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number(value.slice(0, 4)) < 1)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function borrowingCoverageKey(
  balance: number | null | undefined,
  absentReason?: string | null,
  coverage?: BorrowingCoverage,
  asAt?: string | null,
): TranslationKey {
  if ((absentReason && (absentReason !== 'no_eligible_instruments' || balance != null)) ||
      coverage?.status === 'withheld_or_conflicting') return 'county.borrowing.withheld';
  if (typeof balance === 'number' && Number.isFinite(balance) && balance >= 0) {
    return balance === 0 && stockDate(asAt) ? 'county.borrowing.zero' : 'county.borrowing.selected';
  }
  if (balance != null) return 'county.borrowing.withheld';
  if (coverage?.status === 'not_reported_in_checked_source' && borrowingSources(coverage).length) {
    return 'county.borrowing.not_reported';
  }
  return 'county.borrowing.not_integrated';
}
