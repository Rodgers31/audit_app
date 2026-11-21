import type { DebtTimelineEntry } from '@/lib/api/debt';
import { dsaHref, readDsaRating } from '@/lib/debt/dsaRating';
import { publishedHeadlineRatio, publishedTimelineRatio } from '@/lib/debt/qualification';
import { isDebtCategory, summedRegisterRows, type RegisterCategories } from '@/lib/debt/registerScope';
import { evidenceUrl, type QualificationRows } from '@/lib/evidence/qualification';
import { toRawKES } from '@/lib/utils';

type DebtOverview = {
  status?: string;
  total_outstanding?: number | null;
  total_debt?: number | null;
  categories?: RegisterCategories;
  reconciliation?: { primary_source?: string; primary_value_kes?: number | null };
  debt_to_gdp_year?: number;
  debt_to_gdp_source?: string;
  debt_to_gdp_vintage?: string | null;
  debt_to_gdp_observation?: DebtTimelineEntry;
  debt_sustainability?: unknown;
  figure_qualifications?: { loans?: QualificationRows };
};

function realAmount(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function recordId(value: unknown): boolean {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}

function dateStamp(value: string | undefined) {
  if (!/^\d{4}-(0[1-9]|1[0-2])(?:-\d{2})?$/.test(value ?? '') || !value) return null;
  const day = value.length === 7 ? value + '-01' : value;
  const date = new Date(day + 'T00:00:00Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === day ? value : null;
}

/** CBK's dated stock is separate from any sum over the loan register. */
function timelineStock(row: DebtTimelineEntry | null | undefined) {
  const proof = row?.qualifications?.total;
  const identity = proof?.identity;
  const declaredUnit = row?.unit ?? 'billion_KES';
  const value = toRawKES(row?.total, declaredUnit);
  const href = evidenceUrl(proof?.source_url);
  const locator = proof?.locator;
  const cell = typeof locator?.cell === 'string' ? /^(\d{4}-(?:0[1-9]|1[0-2])) \/ total$/.exec(locator.cell) : null;
  const month = cell?.[1];
  if (!row || !realAmount(row.total) || !realAmount(value) || (declaredUnit !== 'KES' && declaredUnit !== 'billion_KES')
    || !href || !month || !month.startsWith(`${row.year}-`)
    || (row.period?.stock_as_of_month && row.period.stock_as_of_month !== month)
    || !identity || identity.measure !== 'total' || identity.geography !== 'KEN' || identity.entity_id !== null
    || identity.period !== String(row.year) || identity.basis !== 'actual' || identity.unit !== declaredUnit
    || proof?.status !== 'verified' || !proof.document_bytes_checked || !proof.value_checked
    || !recordId(proof.source_document_id) || !recordId(proof.receipt_id)
    || typeof proof.digest !== 'string' || !/^[a-f0-9]{64}$/.test(proof.digest)) return null;

  const url = new URL(href);
  if (url.protocol !== 'https:' || (url.port && url.port !== '443')
    || !['centralbank.go.ke', 'www.centralbank.go.ke'].includes(url.hostname)) return null;
  const page = locator?.page;
  if (proof.source_kind === 'pdf' && typeof page === 'number' && Number.isSafeInteger(page) && page > 0) {
    url.hash = `page=${page}`;
  } else if (proof.source_kind !== 'web' || typeof locator?.edition !== 'string' || !locator.edition.trim()) {
    return null;
  }
  return { value, href: url.href, month, table: typeof locator?.table === 'string' ? locator.table : null };
}

export function homeDebtSummary(overview: (DebtOverview & { data?: DebtOverview }) | null | undefined, latest: DebtTimelineEntry | null | undefined) {
  const data = overview?.data ?? overview;
  const registerAmount = data?.total_outstanding ?? data?.total_debt;
  const zeroDeclared = overview?.status === 'success' && data?.reconciliation?.primary_source === 'loans_table'
    && data.reconciliation.primary_value_kes === 0;
  const register = (overview?.status == null || overview.status === 'success') && realAmount(registerAmount)
    && (registerAmount > 0 || zeroDeclared) ? registerAmount : null;
  const rows = register == null ? null : summedRegisterRows(data?.categories, register);
  const loanEvidence = register == null ? [] : Object.entries(data?.figure_qualifications?.loans ?? {}).flatMap(([id, measures]) => {
    const proof = measures?.outstanding;
    const category = proof?.identity?.dimensions?.debt_category;
    return /^\d+$/.test(id) && proof && typeof category === 'string' && isDebtCategory(category)
      ? [{ id, proof }] : [];
  });
  const candidateDate = dateStamp(loanEvidence[0]?.proof.identity.period);
  const registerDate = candidateDate && rows === loanEvidence.length && loanEvidence.every(({ proof }) =>
    ['verified', 'qualified'].includes(proof.status) && proof.identity.period === candidateDate
    && proof.identity.measure === 'outstanding' && proof.identity.geography === 'KEN'
    && proof.identity.unit === 'KES' && proof.identity.basis === 'actual' && !!evidenceUrl(proof.source_url))
    ? candidateDate : null;

  const headline = publishedHeadlineRatio(data);
  const ratioValue = headline ?? publishedTimelineRatio(latest);
  const imf = headline != null && data?.debt_to_gdp_source === 'IMF World Economic Outlook';
  const ratioObservation = imf ? null : headline != null ? data?.debt_to_gdp_observation : latest;
  const dsaRating = readDsaRating(data?.debt_sustainability);
  const dsaSource = dsaRating && dateStamp(dsaRating.source.dsa_date) && Number.isSafeInteger(dsaRating.source.page)
    && dsaRating.source.page > 0 ? evidenceUrl(dsaHref(dsaRating)) : undefined;
  return {
    register, registerDate, rows, loanEvidence, stock: timelineStock(latest),
    ratioValue, imf, ratioObservation, ratioStock: timelineStock(ratioObservation),
    ratioYear: imf ? data?.debt_to_gdp_year : ratioObservation?.year,
    ratioVintage: imf ? dateStamp(data?.debt_to_gdp_vintage?.slice(0, 10)) : null,
    dsa: dsaSource ? dsaRating : null, dsaSource,
  };
}
