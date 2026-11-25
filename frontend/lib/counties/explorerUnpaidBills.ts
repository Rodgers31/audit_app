import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { formatCurrency } from '@/lib/utils';
import { evidenceUrl } from '@/lib/evidence/qualification';
import type { County } from '@/types';

type UnpaidBillsAmount = {
  value: number;
  sourceUrl: string;
  sourceTable?: string | null;
  notes: County['pendingBillsNotes'];
};

export type UnpaidBillsMeasure = {
  asAt?: string;
  amounts: ReadonlyMap<string, UnpaidBillsAmount>;
  maximum: number;
};

/** All ranked counties refer to the same reporting stock selected by the list API. */
export function countyUnpaidBills(counties: readonly County[]): UnpaidBillsMeasure {
  const dates = new Set(counties.flatMap(({ pendingBillsReportingDate }) =>
    pendingBillsReportingDate != null ? [pendingBillsReportingDate] : []
  ));
  const [asAt] = Array.from(dates);
  const amounts = new Map<string, UnpaidBillsAmount>();
  if (dates.size !== 1 || !formatAsAt(asAt, 'en')) return { amounts, maximum: 0 };

  for (const county of counties) {
    const value = county.pendingBills;
    if (county.pendingBillsReportingDate !== asAt || county.pendingBillsAsAt !== asAt ||
        value == null || !Number.isFinite(value) || value < 0) continue;
    const source = county.pendingBillsSource;
    const sourceUrl = evidenceUrl(source?.url);
    if (source?.publisher !== 'Controller of Budget' ||
        !sourceUrl || !/^https:\/\/(www\.)?cob\.go\.ke\//.test(sourceUrl)) continue;
    amounts.set(county.id, { value, sourceUrl, sourceTable: source.table, notes: county.pendingBillsNotes });
  }
  return { asAt, amounts, maximum: Math.max(0, ...Array.from(amounts.values(), amount => amount.value)) };
}

export function unpaidBillsTone(value: number | undefined, maximum: number) {
  if (value == null) return 'unavailable';
  return maximum <= 0 ? 1 : Math.min(4, Math.floor(value / maximum * 4) + 1);
}

export const formatUnpaidBills = formatCurrency;
