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
 * Return a short risk label ('Low' | 'Moderate' | 'High') for a given
 * debt-to-GDP ratio. Undefined / null / NaN inputs fall through to
 * 'Moderate' so the UI has a sensible default before data loads.
 */
export function classifyDebtRisk(
  debtToGdpRatio: number | null | undefined,
): 'Low' | 'Moderate' | 'High' {
  if (debtToGdpRatio == null || Number.isNaN(debtToGdpRatio)) return 'Moderate';
  if (debtToGdpRatio < DEBT_RISK_THRESHOLDS.LOW_MAX) return 'Low';
  if (debtToGdpRatio < DEBT_RISK_THRESHOLDS.MODERATE_MAX) return 'Moderate';
  return 'High';
}

export function getDebtRiskColor(debtToGdpRatio: number): string {
  const band = classifyDebtRisk(debtToGdpRatio);
  if (band === 'Low') return 'text-brand-500';
  if (band === 'Moderate') return 'text-caution';
  return 'text-risk';
}

export function getDebtRiskLevel(debtToGdpRatio: number): string {
  return `${classifyDebtRisk(debtToGdpRatio)} Risk`;
}

/**
 * Return the current Kenyan fiscal year label (e.g. "2024/25").
 * Kenya FY runs July 1 – June 30.
 */
export function getCurrentFiscalYear(): string {
  const now = new Date();
  const startYear = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
  return `${startYear}/${String(startYear + 1).slice(-2)}`;
}

/**
 * Return the latest *completed* (reported) Kenyan fiscal year — i.e. the one
 * prior to the currently active FY. Execution data (actual spending, audits)
 * isn't published until well after year-end, so UI defaults that require
 * actuals should use this, not `getCurrentFiscalYear()`.
 */
export function getLatestReportedFiscalYear(): string {
  const now = new Date();
  const startYear = now.getMonth() >= 6 ? now.getFullYear() - 1 : now.getFullYear() - 2;
  return `${startYear}/${String(startYear + 1).slice(-2)}`;
}

/**
 * Generate an array of Kenyan fiscal year labels starting from the current year going back.
 */
export function generateFiscalYears(count = 5): string[] {
  const now = new Date();
  let startYear = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
  return Array.from({ length: count }, (_, i) => {
    const y = startYear - i;
    return `${y}/${String(y + 1).slice(-2)}`;
  });
}
