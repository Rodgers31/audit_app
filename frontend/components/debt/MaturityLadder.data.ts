export interface LadderBucket {
  year: number;
  face_value: number | null;
  instruments: number | null;
}

export interface InstrumentsResponse {
  status: 'success' | 'unavailable';
  reason?: string;
  coverage?: { coverage_ratio?: number | null };
  withheld_count?: number;
  withheld_by_gate?: { count: number };
  instrument_count?: number;
  ladder?: LadderBucket[];
  source?: { publisher?: string; title?: string; url?: string; as_of?: string | null };
}

function reportingDate(asOf: string | null | undefined): Date | null {
  if (!asOf || !/^\d{4}-\d{2}-\d{2}$/.test(asOf)) return null;
  const date = new Date(`${asOf}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === asOf
    ? date
    : null;
}

export function reportedNumber(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function reportedCount(value: number | null | undefined): number | null {
  return value != null && Number.isInteger(value) && value >= 0 ? value : null;
}

export function describeMaturities(data: InstrumentsResponse) {
  const date = reportingDate(data.source?.as_of);
  const year = date?.getUTCFullYear() ?? null;
  const rows = (data.ladder ?? [])
    .filter(bucket => Number.isInteger(bucket.year) && bucket.year > 0 && bucket.year < 10_000)
    .map(bucket => ({
      year: bucket.year,
      amount: reportedNumber(bucket.face_value),
      instruments: reportedCount(bucket.instruments),
      past: year != null && bucket.year < year,
    }))
    .sort((left, right) => left.year - right.year);

  const range = year == null ? null : { start: year + 1, end: year + 5 };
  const windowAmounts = range == null ? [] : rows
    .filter(row => row.year >= range.start && row.year <= range.end && row.amount != null && row.amount >= 0)
    .map(row => row.amount!);
  const windowAmount = windowAmounts.length > 0
    ? windowAmounts.reduce((sum, value) => sum + value, 0)
    : null;

  const positive = rows.filter(row => row.amount != null && row.amount > 0);
  const peakAmount = positive.reduce<number | null>((max, row) =>
    row.past ? max : Math.max(max ?? -Infinity, row.amount!), null);
  const peaks = positive.filter(row => !row.past && row.amount === peakAmount).map(row => row.year);
  const maxBar = positive.reduce((max, row) => Math.max(max, row.amount!), 0);

  return {
    date, year, rows, range, windowAmount, windowComplete: windowAmounts.length === 5,
    peakAmount, peaks, maxBar,
  };
}
