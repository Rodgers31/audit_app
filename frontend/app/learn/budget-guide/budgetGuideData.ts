import type { FiscalSummaryResponse } from '@/lib/api/fiscal';
import { fiscalColumnLabel, frameworkOf, qualifiedFrameworkValue } from '@/lib/fiscal/framework';

export const BUDGET_GUIDE_PATH = '/learn/budget-guide';

export const BUDGET_GUIDE_STEPS = [
  { key: 'spending', measure: 'total_expenditure_billion', destination: '/budget' },
  { key: 'revenue', measure: 'total_revenue_incl_aia_billion', destination: '/learn/glossary#term-revenue' },
  { key: 'financing', measure: 'total_financing_billion', destination: '/debt' },
  { key: 'counties', measure: 'county_transfers_billion', destination: '/transparency' },
] as const;

export type BudgetGuideStep = (typeof BUDGET_GUIDE_STEPS)[number];

export function findBudgetGuideStep(parameter?: string | string[]) {
  return BUDGET_GUIDE_STEPS.find(step => step.key === parameter) ?? BUDGET_GUIDE_STEPS[0];
}

export function budgetGuideHref(step: BudgetGuideStep) {
  return `${BUDGET_GUIDE_PATH}?step=${step.key}`;
}

const KENYAN_MONTH = new Intl.DateTimeFormat('en-KE', {
  timeZone: 'Africa/Nairobi', year: 'numeric', month: 'numeric',
});

function currentFiscalYear(today: Date) {
  const parts = KENYAN_MONTH.formatToParts(today);
  const year = Number(parts.find(part => part.type === 'year')?.value);
  const month = Number(parts.find(part => part.type === 'month')?.value);
  const start = month >= 7 ? year : year - 1;
  return `${start}/${String((start + 1) % 100).padStart(2, '0')}`;
}

export function readBudgetGuideFigure(
  response: FiscalSummaryResponse | undefined,
  step: BudgetGuideStep,
  today = new Date(),
) {
  const current = currentFiscalYear(today);
  const fiscalYear = `FY ${current}`;
  const row = response?.current;
  if (row?.fiscal_year?.trim().replace(/^FY\s*/i, '') !== current) {
    return { state: 'yearUnavailable', fiscalYear } as const;
  }

  const framework = frameworkOf(row);
  const measure = qualifiedFrameworkValue(framework, step.measure);
  const source = framework?.source;
  const title = source?.edition ?? source?.title;
  if (fiscalColumnLabel(row) !== 'Approved' || measure == null ||
      !source?.url || !source.publisher || !source.page || !title) {
    return { state: 'figureUnavailable', fiscalYear } as const;
  }

  const page = typeof source.page === 'number'
    ? source.page
    : /^(?:p(?:ages?)?\.?\s*)?([1-9]\d*)$/i.exec(source.page.trim())?.[1]
      ?? /\bPDF\s+pp?\.\s*([1-9]\d*)\b/i.exec(source.page)?.[1];

  const receiptUrl = new URL(source.url);
  if (page) receiptUrl.hash = `page=${page}`;

  return {
    state: 'available',
    fiscalYear,
    amountBillion: measure,
    sourceLabel: `${source.publisher} · ${title} · ${source.page}`,
    sourceUrl: receiptUrl.href,
  } as const;
}
