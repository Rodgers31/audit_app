import type { FiscalMeasureQualification } from '@/lib/api/fiscal';
import { evidenceUrl } from '@/lib/evidence/qualification';
import { FISCAL_FRAMEWORK_BASIS } from '@/lib/fiscal/framework';

export const HISTORY_MEASURES = ['appropriated_budget', 'total_revenue', 'total_borrowing', 'debt_service_cost'] as const;
type HistoryMeasure = (typeof HISTORY_MEASURES)[number];

type Source = FiscalMeasureQualification['source'] & { column?: string };
type Proof = FiscalMeasureQualification & { source: Source };

export interface FiscalHistoryRow {
  fiscal_year: string;
  /** The Budget page has already normalized these amounts to billions of KES. */
  appropriated_budget?: number | null;
  total_revenue?: number | null;
  total_borrowing?: number | null;
  debt_service_cost?: number | null;
  split_basis?: string | null;
  debt_service_source?: { title?: string } | null;
  measure_qualifications?: Record<string, Proof>;
  absent_reasons?: Record<string, string>;
}

const PUBLICATION = {
  Approved: 'approved',
  Actual: 'actual',
  Preliminary: 'preliminary',
  'Supplementary I': 'supplementary',
} as const;
type Vintage = (typeof PUBLICATION)[keyof typeof PUBLICATION];
export type HistoryCode = Vintage | 'unconfirmed' | 'withheld';

const EXPECTED_BASIS: Record<HistoryMeasure, string> = {
  appropriated_budget: 'cob_gross',
  total_revenue: 'ordinary_revenue_excl_aia',
  total_borrowing: FISCAL_FRAMEWORK_BASIS,
  debt_service_cost: 'total_debt_service_interest_and_principal',
};

export type HistoryObservation = {
  year: string;
  value: number | null;
  code?: HistoryCode;
  proof?: Proof;
  sourceTitle?: string;
};

type Period = { year: string; row: FiscalHistoryRow | null };

function fiscalYear(value: string | undefined) {
  const match = typeof value === 'string' && /^(?:FY\s*)?(\d{4})\/(\d{2})$/i.exec(value.trim());
  return match && (+match[1] + 1) % 100 === +match[2] ? `${match[1]}/${match[2]}` : null;
}

export function historyPeriods(history: FiscalHistoryRow[]): Period[] {
  const byYear = new Map<string, FiscalHistoryRow | null>();
  for (const row of history) {
    const year = fiscalYear(row?.fiscal_year);
    if (year) byYear.set(year, byYear.has(year) ? null : row);
  }
  return Array.from(byYear).sort(([a], [b]) => a.localeCompare(b)).map(([year, row]) => ({ year, row }));
}

function qualifiedSource(source: Source | undefined) {
  const url = evidenceUrl(source?.url);
  const page = source?.page;
  return !!url && /^https:\/\/(www\.)?(treasury|cob)\.go\.ke\//.test(url) && !url.includes('#') &&
    ((typeof page === 'number' && Number.isInteger(page) && page > 0) || (typeof page === 'string' && !!page.trim())) &&
    typeof source?.sha256 === 'string' && /^[a-f0-9]{64}$/.test(source.sha256);
}

function confirmedVintage(proof: Proof | undefined, year: string, value: number, measure: HistoryMeasure): Vintage | undefined {
  if (!proof || fiscalYear(proof.fiscal_year) !== year || proof.basis !== EXPECTED_BASIS[measure] ||
      typeof proof.value_kes !== 'number' || proof.value_kes / 1e9 !== value ||
      !Number.isFinite(proof.precision_kes) || proof.precision_kes <= 0 || proof.precision_kes > 1e9 ||
      !qualifiedSource(proof.source) || (proof.source.column != null && proof.source.column !== proof.vintage) ||
      !Object.hasOwn(PUBLICATION, proof.vintage)) return undefined;
  return PUBLICATION[proof.vintage as keyof typeof PUBLICATION];
}

export function observeHistory({ year, row }: Period, measure: HistoryMeasure): HistoryObservation {
  if (!row) return { year, value: null, code: 'withheld' };
  const amount = row[measure];
  if (row.absent_reasons?.[measure] || (measure === 'total_borrowing' && row.split_basis !== FISCAL_FRAMEWORK_BASIS)) {
    return { year, value: null, code: 'withheld' };
  }
  if (typeof amount !== 'number' || !Number.isFinite(amount) || amount < 0) return { year, value: null };

  const proof = row.measure_qualifications?.[measure];
  const code = confirmedVintage(proof, year, amount, measure);
  if (proof && code) return { year, value: amount, code, proof };
  if (row.measure_qualifications || row.absent_reasons) return { year, value: null, code: 'withheld' };

  // Older payloads still provide published amounts without per-measure proof.
  return { year, value: amount, code: 'unconfirmed', sourceTitle: measure === 'debt_service_cost' ? row.debt_service_source?.title : undefined };
}

export function comparableHistory(start: HistoryObservation, end: HistoryObservation) {
  return !!start.proof && !!end.proof && start.proof.basis === end.proof.basis && start.proof.vintage === end.proof.vintage;
}

export function historyChange(observations: HistoryObservation[]) {
  const end = observations.at(-1);
  if (end?.value == null || !end.proof) return null;
  const start = observations.find(observation => observation.year !== end.year &&
    observation.value != null && observation.value > 0 && comparableHistory(observation, end));
  if (!start || start.value == null) return null;
  const change = (end.value - start.value) / start.value;
  return Number.isFinite(change) ? { change, start: start.year } : null;
}
