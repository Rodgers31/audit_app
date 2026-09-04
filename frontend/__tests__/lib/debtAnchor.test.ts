/**
 * The homepage headline turns red only when a published figure exceeds a
 * published threshold, so the condition that drives it has to be exactly
 * right in both directions.
 *
 * The trap this guards is the same one `classifyDebtRisk` was written to
 * close: a failed request returns `debt_to_gdp_ratio: 0`, and a naive
 * `ratio > anchor` boolean reads that as FALSE — "within the anchor" — so an
 * outage on the national accounts renders as quiet reassurance. Absence is
 * not compliance, which is why this returns a three-state result rather than
 * a boolean.
 */
import { assessDebtAnchor, PFM_ACT_ANCHOR_PCT_GDP } from '@/lib/debt/debtAnchor';

describe('assessDebtAnchor', () => {
  it('reports the breach and its size for the live figures', () => {
    // 69.3% against the PFM Act 2023 anchor of 55%, as served by
    // /api/v1/fiscal/summary on 2026-09-04.
    const r = assessDebtAnchor(69.3, 55);
    expect(r.state).toBe('above');
    if (r.state !== 'above') throw new Error('unreachable');
    expect(r.pointsAbove).toBeCloseTo(14.3, 5);
    expect(r.anchorPct).toBe(55);
    expect(r.ratioPct).toBe(69.3);
  });

  it('reports a ratio under the anchor as within it', () => {
    const r = assessDebtAnchor(48.2, 55);
    expect(r.state).toBe('within');
  });

  it('treats the anchor itself as within, not above', () => {
    expect(assessDebtAnchor(55, 55).state).toBe('within');
  });

  /* ── absence is not compliance ── */

  it.each([
    ['a zero from a failed request', 0],
    ['a negative reading', -3],
    ['NaN', Number.NaN],
    ['null', null],
    ['undefined', undefined],
  ])('does not report %s as within the anchor', (_label, ratio) => {
    // A boolean `ratio > anchor` returns false for every one of these, which
    // the UI would render as "not breached" — an outage shown as compliance.
    expect(assessDebtAnchor(ratio as number, 55).state).toBe('unassessed');
  });

  it('does not report an unusable ratio as a breach either', () => {
    expect(assessDebtAnchor(0, 55).state).not.toBe('above');
  });

  /* ── the anchor comes from the API, with a fallback ── */

  it('uses the anchor the API supplies', () => {
    const r = assessDebtAnchor(60, 70);
    expect(r.state).toBe('within');
  });

  it('falls back to the PFM Act anchor when the API omits it', () => {
    const r = assessDebtAnchor(69.3, null);
    expect(r.state).toBe('above');
    if (r.state !== 'above') throw new Error('unreachable');
    expect(r.anchorPct).toBe(PFM_ACT_ANCHOR_PCT_GDP);
  });

  it('falls back rather than trusting a nonsense anchor', () => {
    // A 0 anchor would make every ratio a breach by an absurd margin.
    const r = assessDebtAnchor(69.3, 0);
    expect(r.state).toBe('above');
    if (r.state !== 'above') throw new Error('unreachable');
    expect(r.anchorPct).toBe(PFM_ACT_ANCHOR_PCT_GDP);
    expect(r.pointsAbove).toBeCloseTo(14.3, 5);
  });
});
