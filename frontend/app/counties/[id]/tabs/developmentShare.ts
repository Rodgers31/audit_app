import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { evidenceUrl, type FigureQualification } from '@/lib/evidence/qualification';
import type { CountyComprehensive } from '@/types';

type CountyBudget = CountyComprehensive['budget'] & {
  accounting_basis?: string | null;
  fiscal_period?: { id?: number; label?: string; start_date?: string; end_date?: string } | null;
  sources?: Array<{ id?: number; url?: string; title?: string; publisher?: string }>;
};

function amount(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function countyName(name: string) {
  return name.trim().toLowerCase().replace(/\s+county$/, '');
}

function hasPublishedValue(qualification: FigureQualification) {
  return qualification.status === 'verified'
    ? qualification.document_bytes_checked === true && qualification.value_checked === true
    : qualification.status === 'qualified' && qualification.reason === 'historical_source_not_value_checked';
}

export function countyDevelopmentShare(budget: CountyBudget, county: string) {
  const { accounting_basis: basis, fiscal_period: period, sources } = budget;
  if ((basis !== 'reported_total' && basis !== 'recurrent_plus_development')
    || (budget.source != null && budget.source !== 'cob_cbirr') || sources?.length !== 1) return null;
  const source = sources[0];
  const href = evidenceUrl(source.url);
  const start = period?.start_date?.slice(0, 10);
  const end = period?.end_date?.slice(0, 10);
  if (!href || !Number.isSafeInteger(source.id) || !source.id || source.id < 1
    || !period?.label || period.label !== budget.fiscal_year
    || !start || !end || start > end || !formatAsAt(start, 'en') || !formatAsAt(end, 'en')) return null;

  // The public total is source-bound. The legacy classification sums may
  // include fallback values or duplicate rows, so bind each category first.
  const allocations = Object.values(budget.figure_qualifications ?? {})
    .flatMap(row => row?.allocated_amount ? [row.allocated_amount] : []);
  const rowsFor = (category: string) => allocations.filter(({ identity }) =>
    identity?.dimensions?.category?.trim().toLowerCase() === category && !identity.dimensions.subcategory);
  const totals = rowsFor('total');
  const development = rowsFor('development');
  const recurrent = rowsFor('recurrent');
  if (totals.length !== (basis === 'reported_total' ? 1 : 0)
    || development.length !== 1 || recurrent.length !== 1) return null;

  const records = [...totals, ...development, ...recurrent];
  const entity = development[0].identity.entity_id;
  if (!entity || !Number.isSafeInteger(entity) || entity < 1 || !records.every(q => {
    const row = q.identity;
    return hasPublishedValue(q) && q.source_document_id === source.id && evidenceUrl(q.source_url) === href
      && row.measure === 'allocated_amount' && row.entity_id === entity
      && typeof row.geography === 'string' && countyName(row.geography) === countyName(county)
      && row.period === period.label && row.unit === 'KES' && row.basis === 'actual';
  })) return null;

  const { total_allocated: total, development_budget: projects, recurrent_budget: operations } = budget;
  if (!amount(total) || total <= 0 || !amount(projects) || !amount(operations)
    || projects > total || operations > total || Math.abs(total - projects - operations) > 0.01) return null;

  return {
    rate: projects / total * 100, projects, operations, total, period: period.label, start, end,
    href, publisher: source.publisher, sourceTitle: source.title,
    sourceLinkedOnly: records.some(record => record.status === 'qualified'),
  };
}
