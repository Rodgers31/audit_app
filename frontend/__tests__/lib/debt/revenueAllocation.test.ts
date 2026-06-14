import {
  computeRevenueAllocation,
  formatHeadlineKes,
} from '@/lib/debt/revenueAllocation';

describe('computeRevenueAllocation (total debt service framing)', () => {
  // FY 2025/26 seeded values. Updating these in the seed
  // without updating this test catches accidental methodology drift.
  const FY_25_26 = {
    fiscal_year: 'FY 2025/26',
    total_revenue: 2910, // tax + non-tax revenue
    debt_service_cost: 1900, // total debt service
    debt_service_per_shilling: 65.3, // pre-computed by backend
    recurrent_spending: 2850,
    development_spending: 672,
    county_allocation: 415,
    appropriated_budget: 4190,
  };

  it('uses backend-provided debt_service_per_shilling when present', () => {
    const r = computeRevenueAllocation(FY_25_26);
    expect(r).not.toBeNull();
    expect(r!.debtServicePerRev).toBe(65.3);
  });

  it('falls back to ds/rev*100 only when debt_service_per_shilling is missing', () => {
    const { debt_service_per_shilling, ...without } = FY_25_26;
    const r = computeRevenueAllocation(without);
    // 1900 / 2910 * 100 = 65.2921...
    expect(r!.debtServicePerRev).toBeCloseTo(65.2921, 3);
  });

  it('the FY 2025/26 calculation 1.900 / 2.910 × 100 ≈ 65.3', () => {
    // 1.900 ÷ 2.910 × 100 = 65.2921... — rounds to 65.3 at one decimal
    // and to 65 as an integer (the public-facing headline)
    const ratio = (1.9 / 2.91) * 100;
    expect(ratio).toBeCloseTo(65.2921, 3);
    expect(Number(ratio.toFixed(1))).toBe(65.3);
    expect(formatHeadlineKes(65.3)).toBe(65);
  });

  it('subtracts debt service out of recurrent before computing recPerRev', () => {
    // Avoids double-counting: recurrent_spending in the seed includes
    // debt service; subtracting it gives the "everything else recurrent"
    // figure (salaries, transfers, etc.) for the bar.
    const r = computeRevenueAllocation(FY_25_26);
    // (2850 - 1900) / 2910 * 100 = 950 / 2910 * 100 ≈ 32.65
    expect(r!.recPerRev).toBeCloseTo(32.65, 1);
  });

  it('produces an allocation bar whose sum exceeds 100 (borrowing shortfall)', () => {
    const r = computeRevenueAllocation(FY_25_26);
    const sum =
      r!.debtServicePerRev +
      r!.recPerRev +
      r!.devPerRev +
      r!.countiesPerRev;
    expect(sum).toBeGreaterThan(100);
    // borrowingPerRev is exactly the overshoot above 100
    expect(r!.borrowingPerRev).toBeCloseTo(sum - 100, 5);
  });

  it('returns null when input is null/undefined', () => {
    expect(computeRevenueAllocation(null)).toBeNull();
    expect(computeRevenueAllocation(undefined)).toBeNull();
  });

  it('returns null when total_revenue is missing or zero (no fabricated zero defaults)', () => {
    expect(
      computeRevenueAllocation({ ...FY_25_26, total_revenue: 0 }),
    ).toBeNull();
    expect(
      computeRevenueAllocation({
        ...FY_25_26,
        total_revenue: undefined,
      }),
    ).toBeNull();
  });
});

describe('formatHeadlineKes (rounding)', () => {
  it('rounds 65.3 down to 65 (the FY 2025/26 figure)', () => {
    expect(formatHeadlineKes(65.3)).toBe(65);
  });

  it('rounds 56.65 to 57 (round-half-up at the integer boundary)', () => {
    expect(formatHeadlineKes(56.65)).toBe(57);
  });

  it('rounds 56.4 down to 56 (does NOT silently inflate)', () => {
    expect(formatHeadlineKes(56.4)).toBe(56);
  });

  it('does NOT floor — 56.9 must not become 56', () => {
    expect(formatHeadlineKes(56.9)).not.toBe(56);
    expect(formatHeadlineKes(56.9)).toBe(57);
  });

  it('handles zero gracefully (no fabricated default)', () => {
    expect(formatHeadlineKes(0)).toBe(0);
  });
});
