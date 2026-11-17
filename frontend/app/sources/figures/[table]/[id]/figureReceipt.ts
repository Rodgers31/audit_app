import { evidenceUrl, type FigureQualification, type Qualifications, type QualificationTable } from '@/lib/evidence/qualification';
import type { Lang } from '@/lib/i18n/messages';
import { figureLabels, figureReceiptCopy } from './messages';

export interface VerificationResponse {
  value: string | null;
  reason: string | null;
  qualifications: Qualifications;
  source_document?: string | null;
  source_url?: string | null;
  publisher?: string | null;
  fetch_date?: string | null;
}

// The provenance endpoint publishes one top-level value. Use the measure that
// produces that value rather than another qualification from the same row.
const primaryMeasures = {
  budget_lines: 'allocated_amount',
  loans: 'outstanding',
  gdp_data: 'gdp_value',
  poverty_indices: 'poverty_headcount_rate',
  debt_timeline: 'total',
  revenue_by_source: 'amount_billion_kes',
} satisfies Record<Exclude<QualificationTable, 'economic_indicators'>, string>;

function primaryQualification(table: QualificationTable, qualifications: Qualifications): FigureQualification | undefined {
  const keys = Object.keys(qualifications);
  const measure = table === 'economic_indicators'
    ? (keys.length === 1 ? keys[0] : undefined)
    : primaryMeasures[table];
  const qualification = measure ? qualifications[measure] : undefined;
  return qualification?.identity?.measure === measure ? qualification : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function documentUrl(url: string): string {
  const document = new URL(url);
  document.hash = '';
  return document.href;
}

function calendarDate(value: string, lang: Lang, monthOnly = false): string | undefined {
  const day = monthOnly ? `${value}-01` : value;
  const date = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(date.valueOf()) || date.toISOString().slice(0, 10) !== day) return undefined;
  return new Intl.DateTimeFormat(lang === 'sw' ? 'sw-KE' : 'en-GB', {
    timeZone: 'UTC',
    year: 'numeric',
    month: 'long',
    day: monthOnly ? undefined : 'numeric',
  }).format(date);
}

function observationPeriod(period: string | undefined, lang: Lang): string {
  const copy = figureReceiptCopy[lang];
  if (period === 'conflicting_reporting_dates') return copy.conflictingDates;
  if (period === 'invalid_reporting_date') return copy.invalidDates;
  if (!period || period === 'unreported_reporting_date' || period.startsWith('period:')) return copy.noPeriod;
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) return calendarDate(period, lang) ?? copy.invalidDates;
  if (/^\d{4}-\d{2}$/.test(period)) return calendarDate(period, lang, true) ?? copy.invalidDates;
  return period;
}

export function figureReceipt(table: QualificationTable, response: VerificationResponse, lang: Lang) {
  const copy = figureReceiptCopy[lang];
  const primary = primaryQualification(table, response.qualifications ?? {});
  const lender = table === 'loans' ? text(primary?.identity.dimensions?.lender) : undefined;
  const label = lender ?? figureLabels[table][lang];
  const value = text(response.value);
  // The loan response appends the lender name to its balance. Keep the API
  // amount verbatim while putting the same name first in the reader's title.
  const lenderSuffix = lender ? ` (${lender})` : undefined;
  const amount = lenderSuffix && value?.endsWith(lenderSuffix) ? value.slice(0, -lenderSuffix.length) : value;

  const responseUrl = evidenceUrl(response.source_url);
  const measureUrl = evidenceUrl(primary?.source_url);
  const useResponseSource = !measureUrl || (!!responseUrl && documentUrl(responseUrl) === documentUrl(measureUrl));
  const responseName = text(response.source_document) ?? text(response.publisher);
  const sourceName = (useResponseSource ? responseName : undefined) ??
    (measureUrl || !responseUrl ? text(primary?.publisher) : undefined);
  let sourceUrl = measureUrl ?? responseUrl;
  const locator = measureUrl ? primary?.locator : undefined;
  const tableName = typeof locator?.table === 'number' && Number.isSafeInteger(locator.table) && locator.table > 0
    ? String(locator.table) : text(locator?.table);
  const number = locator?.page;
  const page = measureUrl && primary?.source_kind === 'pdf' && typeof number === 'number' &&
    Number.isSafeInteger(number) && number > 0 ? number : undefined;
  if (sourceUrl && page) {
    const pageUrl = new URL(sourceUrl);
    pageUrl.hash = `page=${page}`;
    sourceUrl = pageUrl.href;
  }
  const source = [
    sourceName ?? (sourceUrl ? copy.openSource : undefined),
    tableName && (/^\d+$/.test(tableName) ? copy.table.replace('{number}', tableName) : tableName),
    page && copy.page.replace('{number}', String(page)),
  ].filter(Boolean).join(' · ');
  const retrieved = useResponseSource && text(response.fetch_date)?.match(/^(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$/)?.[1];

  return {
    title: amount ? `${label}: ${amount}` : label,
    hasValue: !!amount,
    source: source || copy.noSource,
    sourceUrl,
    period: observationPeriod(text(primary?.identity.period), lang),
    retrieved: (retrieved && calendarDate(retrieved, lang)) || copy.noRetrieval,
  };
}
