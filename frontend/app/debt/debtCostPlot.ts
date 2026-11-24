import type { DebtServicePoint } from '@/lib/debt/debtServiceSeries';

export type CostYear = {
  year: string;
  shortYear: string;
  point: DebtServicePoint | undefined;
};

const WINDOW_YEARS = 5;

export function chartFiscalYears(points: readonly DebtServicePoint[]): CostYear[] {
  const byYear = new Map<number, DebtServicePoint>();
  for (const point of points) {
    const fiscalYear = /^(?:FY\s*)?(\d{4})\/(\d{2})$/.exec(point.year ?? '');
    if (!fiscalYear) continue;
    const start = Number(fiscalYear[1]);
    if ((start + 1) % 100 === Number(fiscalYear[2])) byYear.set(start, point);
  }

  if (!byYear.size) return [];
  const years = Array.from(byYear.keys());
  const last = Math.max(...years);
  const first = Math.max(Math.min(...years), last - WINDOW_YEARS + 1);
  return Array.from({ length: last - first + 1 }, (_, index) => {
    const start = first + index;
    const end = String((start + 1) % 100).padStart(2, '0');
    return { year: `FY ${start}/${end}`, shortYear: `FY${String(start).slice(-2)}/${end}`, point: byYear.get(start) };
  });
}

export function serviceTicks(values: readonly (number | null)[]): number[] {
  const maximum = Math.max(1, ...values.map(value => value ?? 0));
  const roughStep = maximum / 2.5;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const step = ([1, 2, 2.5, 5, 10].find(unit => unit * magnitude >= roughStep) ?? 10) * magnitude;
  return Array.from({ length: Math.ceil(maximum / step) + 1 }, (_, index) => step * index);
}

export function ratioPath(values: readonly (number | null)[], maximum: number): string {
  return values.map((value, index) => {
    if (value == null) return '';
    const command = index > 0 && values[index - 1] != null ? 'L' : 'M';
    return `${command}${index + 0.5},${100 - value / maximum * 100}`;
  }).filter(Boolean).join(' ');
}
