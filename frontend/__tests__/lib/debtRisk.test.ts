/**
 * Regression tests for the debt-risk classifier.
 *
 * Context: with the database unreachable, `/api/v1/debt/national` returned
 * HTTP 200 with `debt_to_gdp_ratio: 0`. `??` cannot catch `0`, so the value
 * reached `classifyDebtRisk(0)`, which fell into the `< LOW_MAX` branch and
 * returned 'Low'. The homepage therefore rendered:
 *
 *     TOTAL DEBT AS OF — | KES 0.00T | DEBT-TO-GDP 0.0% | RISK LEVEL  LOW RISK
 *
 * A total infrastructure failure displayed as a reassuring rating on the
 * national accounts. These tests pin the rule that absence is never a band.
 *
 * Each of the first three cases FAILS against the previous implementation
 * (null -> 'Moderate', 0 -> 'Low').
 */
import {
  DEBT_RISK_THRESHOLDS,
  classifyDebtRisk,
  getDebtRiskColor,
  getDebtRiskLevel,
} from '@/lib/utils';

describe('classifyDebtRisk — absence is not a risk band', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
    ['NaN', Number.NaN],
  ])('returns null for %s rather than a band', (_label, input) => {
    expect(classifyDebtRisk(input as number | null | undefined)).toBeNull();
  });

  it('returns null for 0 — a failed fetch, not a sovereign with no debt', () => {
    expect(classifyDebtRisk(0)).toBeNull();
  });

  it('returns null for a negative ratio', () => {
    expect(classifyDebtRisk(-5)).toBeNull();
  });
});

describe('classifyDebtRisk — real readings still classify', () => {
  it.each([
    [1, 'Low'],
    [DEBT_RISK_THRESHOLDS.LOW_MAX - 0.1, 'Low'],
    [DEBT_RISK_THRESHOLDS.LOW_MAX, 'Moderate'],
    [DEBT_RISK_THRESHOLDS.MODERATE_MAX - 0.1, 'Moderate'],
    [DEBT_RISK_THRESHOLDS.MODERATE_MAX, 'High'],
    [69.3, 'High'], // Kenya's actual published ratio
  ])('classifies %p as %s', (ratio, band) => {
    expect(classifyDebtRisk(ratio as number)).toBe(band);
  });

  it('POSITIVE CONTROL: a genuine reading is never suppressed', () => {
    // Guards against "fix" by making the classifier always return null.
    expect(classifyDebtRisk(69.3)).not.toBeNull();
  });
});

describe('derived helpers do not invent a rating either', () => {
  it('getDebtRiskLevel says "Not assessed" instead of a band', () => {
    expect(getDebtRiskLevel(null)).toBe('Not assessed');
    expect(getDebtRiskLevel(0)).toBe('Not assessed');
    expect(getDebtRiskLevel(69.3)).toBe('High Risk');
  });

  it('getDebtRiskColor is neutral when unassessable, not reassuring', () => {
    const unassessed = getDebtRiskColor(0);
    expect(unassessed).toBe('text-neutral-muted');
    // must not reuse the "Low"/good colour for a missing reading
    expect(unassessed).not.toBe(getDebtRiskColor(1));
  });
});
