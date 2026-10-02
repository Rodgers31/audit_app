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
  if (revenue.total_revenue == null) {
    const reason = revenue.total_revenue_absent_reason;
    const explanation = reason?.startsWith('streams_do_not_sum_to_grand_total') ||
      reason === 'cbirr_revenue_streams_do_not_sum_to_total'
      ? 'county.revenue.streams_conflict'
      : reason === 'a_section_has_two_subtotals'
        ? 'county.revenue.subtotals_ambiguous'
        : reason === 'unobserved_receipts_cell'
          ? 'county.revenue.missing_cell'
          : 'county.revenue.no_reconciled_table';
    notes.push(`${t('county.revenue.total_unavailable')} ${t(explanation)}`);
    const source = revenue.total_revenue_absence_source;
    const publisher = source?.publisher;
    if (source?.pages.length && publisher) {
      notes.push(t('county.revenue.refusal_source').replace(/\{(publisher|pages)\}/g,
        (_, key) => key === 'publisher' ? publisher : source.pages.join(', ')));
    }
  }
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
