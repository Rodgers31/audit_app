import { countyBudget } from '@/lib/countyFigures';
import { evidenceUrl, qualificationMessageKey, type FigureQualification } from '@/lib/evidence/qualification';
import type { County } from '@/types';

const periodKey = (value?: string) => value?.trim().replace(/^FY\s*/i, '');

function isCountyTotal(figure: FigureQualification | undefined, county: County, period: string) {
  return figure?.identity?.geography === `${county.name} County` &&
    periodKey(figure.identity.period) === period &&
    figure.identity.dimensions?.category?.trim().toLowerCase() === 'total' &&
    !figure.identity.dimensions.subcategory;
}

function isPublishedAmount(figure: FigureQualification, measure: string) {
  const status = qualificationMessageKey(figure);
  return figure.identity.measure === measure && figure.identity.basis === 'actual' &&
    figure.identity.unit === 'KES' && figure.publisher === 'Controller of Budget' &&
    (status === 'evidence.status.verified' ||
      (status === 'evidence.status.qualified' && figure.reason === 'historical_source_not_value_checked'));
}

// This route-local adapter can use the rankings' spending selector once the
// compact rankings land. The pin carries no saved amount or accounting period.
export function yourCountySpendingRate(county: County, fiscalYear?: string) {
  const period = periodKey(fiscalYear);
  const rate = county.budgetUtilization;
  const budget = countyBudget(county);
  if (!period || county.budgetSource !== 'cob_cbirr' || rate == null || !Number.isFinite(rate) || rate < 0 ||
      budget == null || !Number.isFinite(budget) || budget <= 0) return undefined;

  const totals = Object.values(county.figureQualifications?.budget_lines ?? {}).filter(row =>
    isCountyTotal(row.allocated_amount, county, period) || isCountyTotal(row.actual_spent, county, period));
  if (totals.length !== 1) return undefined;
  const { allocated_amount: allocation, actual_spent: expenditure } = totals[0];
  if (!allocation || !expenditure || !isCountyTotal(allocation, county, period) || !isCountyTotal(expenditure, county, period) ||
      !isPublishedAmount(allocation, 'allocated_amount') || !isPublishedAmount(expenditure, 'actual_spent')) return undefined;

  const source = evidenceUrl(allocation.source_url);
  const sameReport = allocation.source_document_id != null && allocation.source_document_id === expenditure.source_document_id &&
    source && /^https:\/\/(?:www\.)?cob\.go\.ke\//.test(source) && source === evidenceUrl(expenditure.source_url);
  const sameCounty = allocation.identity.entity_id != null && allocation.identity.entity_id === expenditure.identity.entity_id;
  return sameReport && sameCounty ? rate : undefined;
}
