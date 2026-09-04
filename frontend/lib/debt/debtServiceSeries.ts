/**
 * Series for "The cost of debt over time".
 *
 * The chart plots two things per fiscal year: debt service (area, left axis)
 * and debt service as a share of revenue (line, right axis). The share is a
 * RATIO, so it exists only for a year where BOTH inputs were published.
 *
 * It previously ended in `: 0`:
 *
 *   ratio: y.debt_service_cost && y.total_revenue
 *     ? (y.debt_service_cost / y.total_revenue) * 100
 *     : 0,
 *
 * FY 2026/27 has an enacted budget and a debt-service figure from the
 * Programme Based Budget book, but Treasury's revenue estimate for that year
 * is not yet in our data — so the line dived from 65% to 0%, drawing the
 * claim that debt service will consume none of revenue in the year it is
 * actually largest. Absence has to plot as a gap: Recharts breaks a line on
 * `null` (its `connectNulls` default is false), so withholding is what a
 * reader sees.
 */

/** A fiscal-year row, already normalised to raw KES by the caller. */
export interface FiscalYearRow {
  fiscal_year?: string | null;
  debt_service_cost?: number | null;
  total_revenue?: number | null;
}

export interface DebtServicePoint {
  year: string | null;
  /** Debt service in KES, or null when the year has no published figure. */
  service: number | null;
  /** Percent of revenue, or null when either input is absent. */
  ratio: number | null;
}

/** A published, usable money figure — not absent, not a non-finite artefact. */
const published = (v: number | null | undefined): v is number =>
  typeof v === 'number' && Number.isFinite(v);

export function buildDebtServiceSeries(years: FiscalYearRow[]): DebtServicePoint[] {
  return (years ?? []).map((y) => {
    const service = published(y?.debt_service_cost) ? y.debt_service_cost : null;
    const revenue = published(y?.total_revenue) ? y.total_revenue : null;
    return {
      year: y?.fiscal_year ?? null,
      service,
      // Guarded on revenue > 0 as well as presence: a zero denominator is a
      // division artefact, not a share.
      ratio: service != null && revenue != null && revenue > 0 ? (service / revenue) * 100 : null,
    };
  });
}

/**
 * The most recent year that has debt service but no revenue, if any.
 *
 * The chart uses this to say why its line stops early, rather than leaving a
 * reader to guess whether the series ended or the data did.
 */
export function yearMissingRevenue(years: FiscalYearRow[]): string | null {
  for (let i = (years ?? []).length - 1; i >= 0; i--) {
    const y = years[i];
    if (published(y?.debt_service_cost) && !published(y?.total_revenue)) {
      return y?.fiscal_year ?? null;
    }
  }
  return null;
}
