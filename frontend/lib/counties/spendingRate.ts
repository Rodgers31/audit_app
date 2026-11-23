import { COUNTY_SPENDING_TARGET } from '@/components/transparency/moneyFlowPresentation';
import { countyBudget } from '@/lib/countyFigures';
import { evidenceUrl, qualificationMessageKey, type FigureQualification } from '@/lib/evidence/qualification';
import type { County } from '@/types';

function periodKey(period: string | undefined) {
  return period?.trim().replace(/^FY\s*/i, '') ?? '';
}

function matchesTotal(q: FigureQualification, county: County, fiscalYear: string) {
  const identity = q.identity;
  const category = identity?.dimensions?.category;
  return (
    identity?.geography === `${county.name} County` &&
    periodKey(identity.period) === periodKey(fiscalYear) &&
    typeof category === 'string' &&
    category.trim().toLowerCase() === 'total' &&
    !identity.dimensions.subcategory
  );
}

function usableCobAmount(q: FigureQualification | undefined, measure: string) {
  if (!q) return false;
  const grade = qualificationMessageKey(q);
  const url = evidenceUrl(q.source_url);
  return (
    q.identity?.measure === measure &&
    q.identity.basis === 'actual' &&
    q.identity.unit === 'KES' &&
    q.publisher === 'Controller of Budget' &&
    url != null &&
    /^https:\/\/(www\.)?cob\.go\.ke\//.test(url) &&
    (grade === 'evidence.status.verified' ||
      (grade === 'evidence.status.qualified' && q.reason === 'historical_source_not_value_checked'))
  );
}

/** The list's rate can be a legacy zero for missing expenditure. A sourced Total distinguishes it. */
export function publishedSpendingRate(county: County, fiscalYear?: string): number | undefined {
  const rate = county.budgetUtilization;
  const allocation = countyBudget(county);
  if (
    !periodKey(fiscalYear) ||
    !fiscalYear ||
    county.budgetSource === 'cra_model' ||
    county.budgetSource === 'mixed' ||
    allocation == null ||
    !Number.isFinite(allocation) ||
    allocation <= 0 ||
    rate == null ||
    !Number.isFinite(rate) ||
    rate < 0
  ) return undefined;

  const totals = Object.values(county.figureQualifications?.budget_lines ?? {}).filter(
    ({ allocated_amount, actual_spent }) =>
      (allocated_amount && matchesTotal(allocated_amount, county, fiscalYear)) ||
      (actual_spent && matchesTotal(actual_spent, county, fiscalYear))
  );
  if (totals.length !== 1) return undefined;

  const { allocated_amount: budget, actual_spent: spent } = totals[0];
  if (
    budget &&
    spent &&
    matchesTotal(budget, county, fiscalYear) &&
    matchesTotal(spent, county, fiscalYear) &&
    usableCobAmount(budget, 'allocated_amount') &&
    usableCobAmount(spent, 'actual_spent') &&
    budget.identity.entity_id != null &&
    budget.identity.entity_id === spent.identity.entity_id &&
    budget.source_document_id != null &&
    budget.source_document_id === spent.source_document_id &&
    budget.source_url === spent.source_url
  ) return rate;
  return undefined;
}

export function hasAnnualSpendingTarget(fiscalYear?: string): boolean {
  return /^\d{4}\/\d{2}$/.test(periodKey(fiscalYear));
}

export const ANNUAL_SPENDING_BANDS = ['above', 'on', 'below', 'well-below'] as const;
export type SpendingBand = (typeof ANNUAL_SPENDING_BANDS)[number] | 'reported' | 'unavailable';

export function spendingBand(rate: number | undefined, fiscalYear?: string): SpendingBand {
  if (rate == null) return 'unavailable';
  if (!hasAnnualSpendingTarget(fiscalYear)) return 'reported';
  if (rate >= 80) return 'above';
  if (rate >= COUNTY_SPENDING_TARGET) return 'on';
  return rate >= 65 ? 'below' : 'well-below';
}

export function formatSpendingRate(rate: number): string {
  // Keep a rounded display value from crossing a visible status boundary.
  const rounded = Number(rate.toFixed(1));
  if ([65, COUNTY_SPENDING_TARGET, 80].some((boundary) => rate < boundary && rounded === boundary)) {
    return `<${rounded}%`;
  }
  return `${rate.toFixed(1)}%`;
}
