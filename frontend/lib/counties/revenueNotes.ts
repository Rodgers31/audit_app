import type { CountyRevenue } from '@/types';
import type { TranslationKey } from '@/lib/i18n/messages';

type Translate = (key: TranslationKey) => string;

export function countyOwnSourceRevenueLabel(
  revenue: Pick<CountyRevenue, 'local_revenue_basis'> | undefined,
  t: Translate
): string {
  return t(revenue?.local_revenue_basis === 'cash_receipts'
    ? 'county.revenue.cash_receipts'
    : 'county.revenue.summary_actual_realised');
}

/** Shared by the county overview and report card; never equate cash and accrual. */
export function countyRevenueNotes(revenue: CountyRevenue, format: (n: number) => string, t: Translate): string[] {
  const notes: string[] = [];
  if (revenue.fiscal_year) notes.push(revenue.fiscal_year);
  if (revenue.local_revenue != null) {
    const label = countyOwnSourceRevenueLabel(revenue, t);
    const amount = format(revenue.local_revenue);
    notes.push(t('county.revenue.amount').replace(/\{(label|amount)\}/g, (_, key) => key === 'label' ? label : amount));
  }
  if (revenue.own_source_disagreement && revenue.summary_table_own_source_revenue != null) {
    const amount = format(revenue.summary_table_own_source_revenue);
    notes.push(t('county.revenue.summary_differs').replace(/\{amount\}/g, () => amount));
  }
  return notes;
}
