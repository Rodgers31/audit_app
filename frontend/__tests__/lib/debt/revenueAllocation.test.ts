import {
  computeRevenueAllocation,
  formatHeadlineKes,
} from '@/lib/debt/revenueAllocation';
import { FF_2026_27 } from '@/test/fixtures/fiscalFramework';

describe('computeRevenueAllocation — the headline (Treasury APDMR ratio)', () => {
  // FY 2025/26 values, as the headline has always been pinned.
  const FY_25_26 = {
    fiscal_year: 'FY 2025/26',
    total_revenue: 2910, // tax + non-tax revenue
    debt_service_cost: 1900, // total debt service
    debt_service_per_shilling: 65.3, // pre-computed by backend
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
    const ratio = (1.9 / 2.91) * 100;
    expect(ratio).toBeCloseTo(65.2921, 3);
    expect(Number(ratio.toFixed(1))).toBe(65.3);
    expect(formatHeadlineKes(65.3)).toBe(65);
  });

  it('returns null when input is null/undefined', () => {
    expect(computeRevenueAllocation(null)).toBeNull();
    expect(computeRevenueAllocation(undefined)).toBeNull();
  });

  it('returns null when total_revenue is missing or zero (no fabricated zero defaults)', () => {
    expect(computeRevenueAllocation({ ...FY_25_26, total_revenue: 0 })).toBeNull();
    expect(computeRevenueAllocation({ ...FY_25_26, total_revenue: undefined })).toBeNull();
  });

  it('keeps the headline but withholds the breakdown when no framework exists', () => {
    const r = computeRevenueAllocation(FY_25_26)!;
    expect(r.debtServicePerRev).toBe(65.3);
    expect(r.breakdown).toBeNull();
  });
});

describe('computeRevenueAllocation — the breakdown (issue #237)', () => {
  const FY_26_27 = {
    fiscal_year: 'FY 2026/27',
    total_revenue: 2985.7e9, // raw KES, as the debt page normalises it
    total_revenue_billion: 2985.7,
    debt_service_cost: 2315.9e9,
    debt_service_per_shilling: 77.6,
    fiscal_framework: FF_2026_27,
  };

  it('counts interest — not interest plus principal — as the debt slice', () => {
    const b = computeRevenueAllocation(FY_26_27)!.breakdown!;
    // 1,254.2 / 2,985.7 × 100. The old bar used the headline's 77.6, which
    // includes 1,061.6B of principal that is not spending.
    expect(b.interestPerRev).toBeCloseTo(42.01, 2);
    // (3,538.7 - 1,254.2) / 2,985.7 × 100. The old bar subtracted 2,315.9,
    // which put recurrent at 41.0 per 100 instead of 76.5.
    expect(b.recPerRev).toBeCloseTo(76.51, 2);
  });

  it('spending per 100 is shown with what financed the part above 100', () => {
    const b = computeRevenueAllocation(FY_26_27)!.breakdown!;
    expect(b.spendingPerRev).toBeCloseTo(160.27, 2);
    const financed = b.aiaPerRev + b.grantsPerRev + b.borrowingPerRev + b.cashAdjustmentPerRev;
    // No residual: the table's own rows account for it, within rounding.
    expect(100 + financed).toBeCloseTo(b.spendingPerRev, 1);
  });

  it('withholds the breakdown when the row revenue is not the framework revenue', () => {
    // A different "KES 100" beside the headline would be two bases on one card.
    const r = computeRevenueAllocation({ ...FY_26_27, total_revenue_billion: 2910 })!;
    expect(r.debtServicePerRev).toBe(77.6);
    expect(r.breakdown).toBeNull();
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
