import { type ClassValue, clsx } from 'clsx';
import numeral from 'numeral';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  if (value >= 1e12) {
    return `KES ${numeral(value / 1e12).format('0.0')}T`;
  }
  if (value >= 1e9) {
    return `KES ${numeral(value / 1e9).format('0.0')}B`;
  }
  if (value >= 1e6) {
    return `KES ${numeral(value / 1e6).format('0.0')}M`;
  }
  return `KES ${numeral(value).format('0,0')}`;
}

/**
 * Format a raw KES amount into a short human-readable string.
 * Input: raw KES (e.g. 5_441_872_939) → "KES 5.4B"
 */
export function fmtKES(val: number): string {
  if (!val || val === 0) return 'KES 0';
  const abs = Math.abs(val);
  if (abs >= 1e12) return `KES ${(val / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(val / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `KES ${(val / 1e6).toFixed(1)}M`;
  return `KES ${val.toLocaleString()}`;
}

/**
 * Normalise a money value from /debt/timeline or /fiscal/summary to raw KES.
 *
 * Since the stage1 3a migration those endpoints store and serve raw KES and
 * DECLARE it with a per-row `unit: "KES"` field. A pre-migration backend
 * serves bare billions with no unit field — the one legacy case this
 * converts. The decision is made on the declared unit, never by guessing a
 * value's magnitude (F5.5: undeclared units are how the homepage was once
 * wrong by 10⁹).
 */
export function toRawKES(
  value: number | null | undefined,
  unit?: string | null
): number | null {
  if (value == null || Number.isNaN(value)) return null;
  return unit === 'KES' ? value : value * 1e9;
}

/**
 * Format a **billion KES** value into a short human-readable string.
 * Input: billions (e.g. 3310 meaning KES 3.31 trillion) → "3.31T"
 *
 * ⚠ Do NOT pass raw KES to this function — use fmtKES() instead.
 */
export function fmtBillionKES(val: number): string {
  if (!val) return '—';
  if (val >= 1000) return `${(val / 1000).toFixed(2)}T`;
  return `${val.toFixed(0)}B`;
}

/**
 * Format raw KES into glossary-prose words WITHOUT the "KES" prefix:
 *   16_224_478_000_000 → "16.22 trillion"
 *   405_000_000_000    → "405 billion"
 * Callers that want "KES …" supply the prefix in their own copy.
 */
export function formatKesWords(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)} trillion`;
  if (abs >= 1e9) return `${Math.round(value / 1e9)} billion`;
  if (abs >= 1e6) return `${Math.round(value / 1e6)} million`;
  return value.toLocaleString();
}

export function formatPercentage(value: number): string {
  return `${numeral(value).format('0.0')}%`;
}

export function formatNumber(value: number): string {
  return numeral(value).format('0,0');
}

/**
 * Canonical debt-to-GDP risk thresholds used across the UI.
 *
 *   Low      <  40%   — roughly aligned with EAC convergence (50%).
 *   Moderate 40\u201355%   — below the IMF LIC warning line.
 *   High     \u2265 55%    — the IMF Debt Sustainability Analysis treats
 *                        debt/GDP > 55% as elevated risk for
 *                        low-income countries like Kenya. This is the
 *                        number surfaced throughout the /debt page
 *                        (see InfoTip "imf-threshold").
 *
 * Keep every UI component importing from here so thresholds never
 * drift between widgets. If the IMF revises its guidance, update
 * MODERATE_MAX in this one spot.
 */
export const DEBT_RISK_THRESHOLDS = {
  LOW_MAX: 40,
  MODERATE_MAX: 60,
} as const;

/**
 * Return a short risk label for a given debt-to-GDP ratio, or ``null`` when
 * the ratio cannot be assessed.
 *
 * Absence is not a risk band. This previously returned 'Moderate' for
 * null/NaN so the UI "had a sensible default before data loads" — but a
 * default is a claim. Worse, a ratio of ``0`` (which is what a failed API
 * call used to produce) fell into the ``< LOW_MAX`` branch and rendered as
 * **'Low' risk**, so a database outage displayed as a reassuring rating on
 * the homepage. A non-positive debt-to-GDP reading is not a real
 * observation for a sovereign, so it is treated as unassessable.
 *
 * Callers must render ``null`` as "not assessed" — never as a band.
 */
export function classifyDebtRisk(
  debtToGdpRatio: number | null | undefined,
): 'Low' | 'Moderate' | 'High' | null {
  if (debtToGdpRatio == null || Number.isNaN(debtToGdpRatio)) return null;
  if (debtToGdpRatio <= 0) return null;
  if (debtToGdpRatio < DEBT_RISK_THRESHOLDS.LOW_MAX) return 'Low';
  if (debtToGdpRatio < DEBT_RISK_THRESHOLDS.MODERATE_MAX) return 'Moderate';
  return 'High';
}

/** Colour for a risk band; neutral when the ratio cannot be assessed. */
export function getDebtRiskColor(debtToGdpRatio: number | null | undefined): string {
  const band = classifyDebtRisk(debtToGdpRatio);
  if (band === null) return 'text-neutral-muted';
  if (band === 'Low') return 'text-brand-500';
  if (band === 'Moderate') return 'text-caution';
  return 'text-risk';
}

/** Human label for a risk band; "Not assessed" when the ratio is unusable. */
export function getDebtRiskLevel(debtToGdpRatio: number | null | undefined): string {
  const band = classifyDebtRisk(debtToGdpRatio);
  return band === null ? 'Not assessed' : `${band} Risk`;
}

/**
 * Return the current Kenyan fiscal year label (e.g. "2024/25").
 * Kenya FY runs July 1 – June 30.
 *
 * This asks the calendar which year we are IN, which the calendar can answer.
 * Two neighbours that asked it which year has DATA — `getLatestReportedFiscalYear`
 * and `generateFiscalYears` — are gone: they put four pages on a fiscal year the
 * database held no reported figures for. Anything choosing a year to fetch wants
 * `resolveExplorerYear` / `moneyFlowDefaultYear` / `transparencyYearOptions`,
 * which resolve it from GET /api/v1/counties/fiscal-years.
 */
export function getCurrentFiscalYear(): string {
  const now = new Date();
  const startYear = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
  return `${startYear}/${String(startYear + 1).slice(-2)}`;
}

/** What `GET /api/v1/counties/fiscal-years` reports. */
export interface CountyFiscalYears {
  years: Array<{
    label: string;
    /** 'cob_cbirr' — the Controller of Budget reported this year;
     *  'cra_model' — its figures are the CRA equitable-share model. */
    source: 'cob_cbirr' | 'cra_model';
    counties: number;
  }>;
  /** The year the API resolves to when asked for none. Null when it holds no
   *  county budget data at all. */
  default: string | null;
}

/**
 * The fiscal year the county explorer should show.
 *
 * The explorer used to seed its picker with `getLatestReportedFiscalYear()`,
 * a label derived from `new Date()`. On 2026-09-05 that is "2025/26" — the CRA
 * equitable-share projection — so the explorer asked for that year and
 * published Baringo at KES 7.13B, while the county's own page sends no year,
 * lets the API resolve the period from the rows that exist, and published
 * KES 9.54B from the Controller of Budget's CBIRR. Same county, two budgets
 * (credibility audit F7, reopened through the frontend's explicit
 * `fiscal_year`).
 *
 * `meta.default` is resolved by the same rule `GET /counties` applies when
 * given no year, so the label the page prints and the figures it fetched
 * cannot describe different periods.
 *
 * Returns `undefined` when the API offers no years — the picker then has
 * nothing to show, which is the honest answer. Falling back to a calendar
 * label here would put a year on screen that nothing in the database supports.
 */
export function resolveExplorerYear(
  picked: string | undefined,
  meta: CountyFiscalYears | undefined
): string | undefined {
  const offered = meta?.years.map((y) => y.label) ?? [];
  // A stored or bookmarked choice only stands while the API still offers it.
  if (picked && offered.includes(picked)) return picked;
  return meta?.default ?? undefined;
}

/**
 * A requested fiscal year, or `undefined` when the API would refuse it.
 *
 * The API no longer answers a `fiscal_year` it holds no county budget data
 * for — it used to skip the period filter entirely and sum every period into
 * one figure. It now returns 404, so a county page reached with a stale `?fy=`
 * bookmark would render "Failed to load county data": wrong twice over, since
 * the county loads fine and only the year is unavailable.
 *
 * Dropping the year sends the reader to the period the API resolves itself,
 * which the page labels on screen — a dropped request, not a substituted
 * figure.
 *
 * `meta === undefined` means the year list has not arrived, which is not the
 * same as the year being refused: passing the request through keeps the common
 * path to a single fetch, and a genuinely bad year self-corrects once the list
 * lands.
 */
export function serviceableFiscalYear(
  requested: string | undefined,
  meta: CountyFiscalYears | undefined
): string | undefined {
  if (!requested || !meta) return requested;
  return meta.years.some((y) => y.label === requested) ? requested : undefined;
}

/**
 * The fiscal year the Follow the Money tab should show.
 *
 * It used to pick with `getLatestReportedFiscalYear()` matched against
 * `/audits/fiscal-years` — every fiscal period, not the ones county budget data
 * exists for — so in September 2026 it landed on FY2025/26, the CRA projection.
 *
 * Worse, it chose independently of the page it sits on: the Budget & Debt tab
 * two clicks away could show FY2024/25 while this one showed FY2025/26, for the
 * same county, with nothing saying they differed. So the page's own resolved
 * year leads, and `resolveExplorerYear` drops it if the API no longer offers it.
 *
 * Precedence: the reader's selection, then the year the page is showing, then
 * the API's default.
 */
export function moneyFlowDefaultYear(
  picked: string | undefined,
  pageYear: string | undefined,
  meta: CountyFiscalYears | undefined
): string | undefined {
  return resolveExplorerYear(picked ?? pageYear, meta);
}

/**
 * Year options for the national Follow the Money page, in the bare
 * "YYYY/YY" form its picker compares on.
 *
 * That page took its years from `/audits/fiscal-years` — every `FiscalPeriod`
 * row — and its default from a wall-clock "current FY". On 2026-09-06 the
 * current FY was 2026/27, which appears in no list at all, so the page fired
 * two money-flow requests for a year with nothing behind it before correcting
 * to the newest list entry: FY2025/26, the CRA projection (405,100m) rather
 * than the CBIRR-reported FY2024/25 (633,304m).
 *
 * Four of the eight pills it offered — FY2025/26 9M, FY2025/26 H1, FY2021/22,
 * FY2020/21 — are periods carrying no county budget rows, so clicking them
 * emptied the page.
 *
 * Both now come from `/counties/fiscal-years`, the same source the county
 * pages use. Empty when the API says nothing: a calendar-derived label here is
 * what put the page on a year its own picker did not offer.
 */
export function transparencyYearOptions(meta: CountyFiscalYears | undefined): {
  years: string[];
  default: string | undefined;
} {
  const strip = (y: string) => y.replace(/^FY\s*/i, '').trim();
  return {
    years: meta?.years.map((y) => strip(y.label)) ?? [],
    default: meta?.default ? strip(meta.default) : undefined,
  };
}
