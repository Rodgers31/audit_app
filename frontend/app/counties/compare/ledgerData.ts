import type { BorrowingCoverage } from '@/lib/countyBorrowingCoverage';
import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { evidenceUrl, type QualificationRows } from '@/lib/evidence/qualification';
import { fmtKES } from '@/lib/utils';
import type { BudgetSource, CountyComprehensive } from '@/types';

export interface CountySummary {
  id: string;
  name: string;
  code?: string;
  figure_qualifications?: { budget_lines?: QualificationRows };
  population?: number | null;
  total_budget?: number | null;
  total_spent?: number | null;
  budget_utilization?: number | null;
  development_budget?: number | null;
  pending_bills?: number | null;
  pending_bills_as_at?: string | null;
  pending_bills_source?: CountyComprehensive['debt']['pending_bills_source'];
  pending_bills_notes?: CountyComprehensive['debt']['pending_bills_notes'];
  pending_bills_absence?: CountyComprehensive['debt']['pending_bills_absence'];
  debt?: number | null;
  total_debt_absent_reason?: string | null;
  debt_currency?: string | null;
  debt_accounting_basis?: string | null;
  debt_basis?: string | null;
  debt_as_at?: string | null;
  debt_coverage?: string | null;
  debt_source_coverage?: BorrowingCoverage;
  financial_health_score?: number | null;
  audit_findings_count?: number | null;
  budget_source?: BudgetSource;
  financial_summary?: {
    fiscal_period?: { label?: string | null; start_date?: string | null; end_date?: string | null } | null;
    total_allocation?: number | null;
    total_spent?: number | null;
    execution_rate?: number | null;
    accounting_basis?: string | null;
    currency?: string | null;
    sources?: Array<{ url?: string | null }>;
  } | null;
}

export const MAX_COMPARE_COUNTIES = 4;

export function comparisonHref(ids: string[]) {
  const selected = ids.filter(Boolean).map(encodeURIComponent).join(',');
  return selected ? `/counties/compare?ids=${selected}` : '/counties/compare';
}

export function reported(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

// The legacy aliases used zero for missing allocation and spending. Only the
// financial summary distinguishes an expressly reported zero from absence.
function legacyBudgetValue(value?: number | null): number | null {
  return reported(value) || null;
}

export function budgetAmount(county: CountySummary) {
  const summary = county.financial_summary;
  return summary ? reported(summary.total_allocation) : legacyBudgetValue(county.total_budget);
}

export function spentAmount(county: CountySummary) {
  const summary = county.financial_summary;
  return summary ? reported(summary.total_spent) : legacyBudgetValue(county.total_spent);
}

export function utilization(county: CountySummary) {
  const allocation = budgetAmount(county);
  if (!allocation || spentAmount(county) === null) return null;
  const summary = county.financial_summary;
  return summary ? reported(summary.execution_rate) : legacyBudgetValue(county.budget_utilization);
}

function currency(value?: string | null): string | undefined {
  return typeof value === 'string' && /^[A-Z]{3}$/.test(value) ? value : undefined;
}

export function budgetMoney(value: number, county: CountySummary): string {
  const unit = currency(county.financial_summary?.currency);
  return unit ? fmtKES(value).replace('KES', unit) : fmtKES(value);
}

export function budgetPeriod(county: CountySummary) {
  const period = county.financial_summary?.fiscal_period;
  const start = period?.start_date;
  const end = period?.end_date;
  if (!start || !end || !formatAsAt(start, 'en') || !formatAsAt(end, 'en') || start > end) return null;
  return { from: start, to: end, label: typeof period.label === 'string' ? period.label : '' };
}

export function budgetComparisonBasis(county: CountySummary): string | undefined {
  const summary = county.financial_summary;
  const period = budgetPeriod(county);
  const sources = summary?.sources;
  const source = Array.isArray(sources) && sources.length === 1 ? evidenceUrl(sources[0]?.url) : undefined;
  if (!summary || !period || !currency(summary.currency) || !source ||
      (summary.accounting_basis !== 'reported_total' && summary.accounting_basis !== 'recurrent_plus_development')) {
    return undefined;
  }
  return JSON.stringify([period.from, period.to, summary.currency, summary.accounting_basis, county.budget_source ?? null, source]);
}

export function debtAmount(county: CountySummary) {
  if (county.total_debt_absent_reason || county.debt_source_coverage?.status === 'withheld_or_conflicting') return null;
  return reported(county.debt);
}

export function debtComparisonBasis(county: CountySummary): string | undefined {
  if (county.debt_currency !== 'KES' || county.debt_basis !== 'actual' ||
      county.debt_accounting_basis !== 'selected_instrument_outstanding' ||
      county.debt_coverage !== 'selected_eligible_instruments_only' ||
      !formatAsAt(county.debt_as_at, 'en')) return undefined;
  return county.debt_as_at ?? undefined;
}

export function publishedFindingCount(county: CountySummary) {
  const count = reported(county.audit_findings_count);
  return Number.isSafeInteger(count) ? count : null;
}

type LedgerValue = { amount: number | null; display: string; basis?: string };

export function comparisonRanks(values: LedgerValue[]): Array<'highest' | 'lowest' | undefined> {
  const known = values.filter((value): value is LedgerValue & { amount: number } => value.amount !== null);
  if (known.length < 2 || !known[0].basis || known.some(({ basis }) => basis !== known[0].basis)) {
    return values.map(() => undefined);
  }
  const minimum = known.reduce((a, b) => a.amount < b.amount ? a : b);
  const maximum = known.reduce((a, b) => a.amount > b.amount ? a : b);
  if (minimum.display === maximum.display) return values.map(() => undefined);
  return values.map(({ amount, display }) => {
    if (amount === null) return undefined;
    if (display === maximum.display) return 'highest';
    if (display === minimum.display) return 'lowest';
  });
}
