import type { CountyRevenue } from '@/types';

/** Shared by the county overview and report card; never equate cash and accrual. */
export function countyRevenueNotes(revenue: CountyRevenue, format: (n: number) => string): string[] {
  const notes: string[] = [];
  if (revenue.fiscal_year) notes.push(revenue.fiscal_year);
  if (revenue.local_revenue != null) {
    const label = revenue.local_revenue_basis === 'cash_receipts'
      ? 'Own-source cash receipts'
      : 'Summary table “Actual Realised”';
    notes.push(`${label}: ${format(revenue.local_revenue)}`);
  }
  if (revenue.own_source_disagreement && revenue.summary_table_own_source_revenue != null) {
    notes.push(`Summary table “Actual Realised”: ${format(revenue.summary_table_own_source_revenue)}; differs from cash receipts`);
  }
  return notes;
}
