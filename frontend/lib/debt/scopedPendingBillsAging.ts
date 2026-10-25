import type { PendingBillsAgingObservation, PendingBillsAgingScope } from '@/lib/api/debt';

const bands = ['Under one year', '1-2 years', '2-3 years', 'Over 3 years'];
const amount = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const decimalAmount = (value: unknown) => typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value) && amount(Number(value));
const names = (value: unknown): value is string[] => Array.isArray(value) && value.every((name) => typeof name === 'string' && name.trim().length > 0) && new Set(value).size === value.length;

type AvailableAging = PendingBillsAgingObservation & {
  as_at: string; source_url: string; publisher: string; table: string; page: number;
  buckets: NonNullable<PendingBillsAgingObservation['buckets']>;
  coverage: NonNullable<PendingBillsAgingObservation['coverage']>;
  reader_notes: NonNullable<PendingBillsAgingObservation['reader_notes']>;
};

/** A source year band cannot become a day band, another scope or a missing zero. */
export function readScopedAging(raw: unknown, scope: PendingBillsAgingScope): AvailableAging | null {
  if (!raw || typeof raw !== 'object' || (scope !== 'county_executive' && scope !== 'county_assembly')) return null;
  const data = raw as PendingBillsAgingObservation;
  const assembly = scope === 'county_assembly';
  if (data.version !== (assembly ? 2 : 1) || data.scope !== scope || data.status !== 'qualified' || data.absent_reason != null ||
      data.unit !== 'KES' || data.currency !== 'KES' || data.complete_total !== null ||
      data.as_at !== '2026-06-30' ||
      typeof data.artifact_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(data.artifact_sha256) ||
      !Number.isInteger(data.extraction_id) || data.extraction_id! <= 0 ||
      typeof data.source_url !== 'string' || !data.source_url.startsWith('https://cob.go.ke/') ||
      typeof data.publisher !== 'string' || !data.publisher.trim() || data.table !== (assembly ? 'Table 2.12' : 'Table 2.11') ||
      !Number.isInteger(data.page) || !(assembly ? [54, 55] : [53, 54]).includes(data.page!)) return null;
  const coverage = data.coverage;
  if (!coverage || coverage.expected_counties !== 47 || coverage.complete !== false ||
      !Number.isInteger(coverage.reported_counties) || coverage.reported_counties < 0 || coverage.reported_counties > 47 ||
      !names(coverage.missing_counties) || !names(coverage.qualified_counties) ||
      coverage.missing_counties.length + coverage.reported_counties !== 47) return null;
  if ((assembly || coverage.counties_with_all_bands !== undefined || coverage.missing_band_counties !== undefined) &&
      (!Number.isInteger(coverage.counties_with_all_bands) || coverage.counties_with_all_bands! < 0 || coverage.counties_with_all_bands! > 47 ||
       !names(coverage.missing_band_counties) || coverage.missing_band_counties.length + coverage.counties_with_all_bands! !== 47)) return null;
  if (!Array.isArray(data.buckets) || data.buckets.length !== 4 || data.buckets.some((band, i) =>
    !band || band.bucket !== bands[i] || (band.amount !== null && !amount(band.amount)) ||
    (band.amount === null && band.absent_reason !== 'source_cell_not_reported'))) return null;
  if (data.reported_total !== null && !amount(data.reported_total)) return null;
  if (!Array.isArray(data.reader_notes) || data.reader_notes.some((note) =>
    !note || typeof note.code !== 'string' || !note.code.trim() ||
    (note.comparison_amount !== undefined && (!decimalAmount(note.comparison_amount) || !amount(data.reported_total))) ||
    (note.aging_reported_total !== undefined && !decimalAmount(note.aging_reported_total)) ||
    (note.comparison_table !== undefined && note.comparison_table !== 'Table 2.10'))) return null;
  const amounts = data.buckets.map((band) => band.amount);
  const chartSupported = data.chart_supported === true && amounts.every(amount) &&
    amount(data.reported_total) && Math.abs(amounts.reduce((sum, value) => sum + value, 0) - data.reported_total) <= 50_000;
  return { ...data, chart_supported: chartSupported } as AvailableAging;
}
