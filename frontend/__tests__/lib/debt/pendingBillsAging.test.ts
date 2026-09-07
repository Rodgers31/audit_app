/**
 * A pending-bills aging distribution may only be drawn when the payload can
 * support one.
 *
 * The backend has no aging observation for any bill it serves. Both endpoints
 * fall back to the loans table and emit a hardcoded
 * `{"0-30d":0,"31-90d":0,"91-180d":0,"180d+": total}` — an assertion that 100%
 * of the bills are past the 180-day mark that refers them to the Pending Bills
 * Verification Committee, on no evidence. Drawn, that is a solid red bar and a
 * "180d+: KES 9.26B (100.0%)" tooltip on every one of the 47 county pages.
 *
 * On /counties/[id] this was held back only by a type error — the response
 * type declares `aging_buckets` as an array while the API sends an object, so
 * the component's `.length > 0` guard read `undefined` and rendered nothing.
 * Normalising the payload (which the county tab now does, so the section works
 * at all) would have put the fabricated bar on all 47 pages. The guard has to
 * be a decision, not an accident.
 *
 * Fixtures are the real payloads from GET /api/v1/pending-bills/counties/3 and
 * GET /api/v1/pending-bills/summary on 2026-09-06 (production, `5ff5fa9`).
 */

import {
  agingDistributionSupport,
  agingUnsupportedNote,
  declaresBillLevelDetail,
  normalizeAgingBuckets,
} from '@/lib/debt/pendingBillsAging';

/** GET /api/v1/pending-bills/counties/3 (Kilifi), 2026-09-06 — verbatim. */
const KILIFI = {
  status: 'success',
  data_source: 'loans_table_fallback',
  county: 'Kilifi County',
  county_id: '3',
  total_pending: 9_255_600_000,
  breakdown_by_type: { supplier_arrears: 9_255_600_000 },
  aging_buckets: { '0-30d': 0, '31-90d': 0, '91-180d': 0, '180d+': 9_255_600_000 },
  currency: 'KES',
};

/** The national summary, same day — same hardcoded shape at 1.1T. */
const NATIONAL = {
  data_source: 'loans_table_fallback',
  total_pending_amount: 1_108_200_000_000,
  aging_buckets: { '0-30d': 0, '31-90d': 0, '91-180d': 0, '180d+': 1_108_200_000_000 },
};

/** What a genuinely measured county would look like (pending_bills table). */
const MEASURED = {
  data_source: 'pending_bills_table',
  total_pending: 1_000,
  aging_buckets: { '0-30d': 100, '31-90d': 200, '91-180d': 300, '180d+': 400 },
};

describe('normalizeAgingBuckets', () => {
  it('turns the API object into rows with shares', () => {
    const rows = normalizeAgingBuckets(KILIFI.aging_buckets, KILIFI.total_pending);
    expect(rows.map((r) => r.bucket)).toEqual(['0-30d', '31-90d', '91-180d', '180d+']);
    expect(rows[3].amount).toBe(9_255_600_000);
    expect(rows[3].percentage).toBeCloseTo(100, 5);
  });

  it('passes an array payload through unchanged', () => {
    const rows = normalizeAgingBuckets(
      [{ bucket: '0-30d', amount: 250, percentage: 25 }],
      1_000,
    );
    expect(rows).toEqual([{ bucket: '0-30d', amount: 250, percentage: 25, count: undefined }]);
  });

  it('yields no rows for an absent payload', () => {
    expect(normalizeAgingBuckets(undefined, 1_000)).toEqual([]);
    expect(normalizeAgingBuckets(null, 1_000)).toEqual([]);
  });
});

describe('agingDistributionSupport — the fabricated distribution', () => {
  it('refuses to draw the county payload production actually serves', () => {
    const buckets = normalizeAgingBuckets(KILIFI.aging_buckets, KILIFI.total_pending);
    const support = agingDistributionSupport(buckets, KILIFI);
    expect(support.supported).toBe(false);
    expect(support).toEqual({ supported: false, reason: 'not-measured' });
  });

  it('refuses to draw the national payload on /debt', () => {
    const buckets = normalizeAgingBuckets(NATIONAL.aging_buckets, NATIONAL.total_pending_amount);
    expect(agingDistributionSupport(buckets, NATIONAL).supported).toBe(false);
  });

  it('still refuses when the payload declares nothing — the shape alone is enough', () => {
    // Fail closed. A distribution with all its mass in one bucket cannot be
    // told apart from the hardcoded shape, so it is not drawn.
    const buckets = normalizeAgingBuckets(KILIFI.aging_buckets, KILIFI.total_pending);
    expect(agingDistributionSupport(buckets, {})).toEqual({
      supported: false,
      reason: 'single-bucket',
    });
  });

  it('refuses even when the single bucket is not the 180d+ one', () => {
    // The old check on /debt keyed on `bucket.includes('180')`, so the same
    // fabrication under any other label would have been drawn as measured.
    const buckets = normalizeAgingBuckets({ '0-30d': 500, '31-90d': 0, '180d+': 0 }, 500);
    expect(agingDistributionSupport(buckets, {}).supported).toBe(false);
  });

  it('refuses a source that declares no bill-level detail even if the shape looks real', () => {
    // Provenance beats shape: a fallback source cannot have measured aging, so
    // a plausible-looking spread from it is still not a measurement.
    const buckets = normalizeAgingBuckets(
      { '0-30d': 100, '31-90d': 200, '91-180d': 300, '180d+': 400 },
      1_000,
    );
    expect(agingDistributionSupport(buckets, { data_source: 'loans_table_fallback' })).toEqual({
      supported: false,
      reason: 'not-measured',
    });
  });

  it('reports no-data rather than a fabrication when every bucket is zero', () => {
    const buckets = normalizeAgingBuckets({ '0-30d': 0, '180d+': 0 }, 0);
    expect(agingDistributionSupport(buckets, KILIFI)).toEqual({
      supported: false,
      reason: 'no-data',
    });
  });

  it('handles an absent bucket list', () => {
    expect(agingDistributionSupport(undefined, KILIFI).supported).toBe(false);
    expect(agingDistributionSupport([], KILIFI).supported).toBe(false);
  });
});

describe('agingDistributionSupport — a real distribution is still drawn', () => {
  it('draws a measured spread from the pending_bills table', () => {
    const buckets = normalizeAgingBuckets(MEASURED.aging_buckets, MEASURED.total_pending);
    expect(agingDistributionSupport(buckets, MEASURED)).toEqual({ supported: true });
  });

  it('draws a spread from an undeclared source when the shape is a real distribution', () => {
    const buckets = normalizeAgingBuckets(MEASURED.aging_buckets, MEASURED.total_pending);
    expect(agingDistributionSupport(buckets, {}).supported).toBe(true);
  });

  it('draws a two-bucket spread — the guard is "one bucket", not "few buckets"', () => {
    const buckets = normalizeAgingBuckets({ '91-180d': 400, '180d+': 600 }, 1_000);
    expect(agingDistributionSupport(buckets, {}).supported).toBe(true);
  });
});

describe('declaresBillLevelDetail', () => {
  it('reads the declaration when the payload makes one', () => {
    expect(declaresBillLevelDetail('pending_bills_table')).toBe(true);
    expect(declaresBillLevelDetail('loans_table_fallback')).toBe(false);
    expect(declaresBillLevelDetail('none')).toBe(false);
    expect(declaresBillLevelDetail('database_empty')).toBe(false);
  });

  it('returns null — not a guess — when nothing is declared', () => {
    expect(declaresBillLevelDetail(undefined)).toBeNull();
    expect(declaresBillLevelDetail('')).toBeNull();
    expect(declaresBillLevelDetail(42)).toBeNull();
    expect(declaresBillLevelDetail('some_future_source')).toBeNull();
  });
});

describe('agingUnsupportedNote', () => {
  it('says the total is unaffected, so withholding the chart is not read as doubting the figure', () => {
    expect(agingUnsupportedNote('not-measured')).toMatch(/total above is unaffected/i);
    expect(agingUnsupportedNote('single-bucket')).toMatch(/total above is unaffected/i);
  });

  it('does not promise a fix on a schedule nobody has committed to', () => {
    // The withdrawn copy said "A richer breakdown will appear once the
    // pending_bills seed lands" — a delivery date for a dataset that has no
    // owner.
    for (const reason of ['no-data', 'not-measured', 'single-bucket'] as const) {
      expect(agingUnsupportedNote(reason)).not.toMatch(/will appear|coming soon|once the .* lands/i);
    }
  });
});
