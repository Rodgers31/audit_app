/**
 * `DebtSustainabilityResponse` must describe the payload the endpoint sends.
 *
 * This file is half compile-time. The fixture below is annotated with the
 * interface, so `tsc --noEmit` fails if the type drifts from the response —
 * which is the only check that matters for a shape nothing renders yet.
 *
 * It is worth having because a type that lies here has already cost this
 * codebase months. `CountyPendingBillsResponse.aging_buckets` was declared as
 * an array while the API sent an object; `aging_buckets.length > 0` compiled
 * fine, evaluated `undefined > 0`, and the county pending-bills section
 * rendered nothing on all 47 pages without anyone noticing.
 *
 * The previous declaration here was wrong in three separate ways that had
 * nothing to do with the rename, and would have been inherited by the first
 * component to use it:
 *
 *   debt_to_gdp              typed `number`; the API sends
 *                            {value, year, threshold_imf, threshold_eac, status}
 *   debt_service_to_revenue  typed `number`; the API sends
 *                            {value, year, threshold, status}
 *   projections[]            typed {year, debt_to_gdp, debt_service_to_revenue};
 *                            the API sends {year, projected_debt_to_gdp}
 *
 * Fixture: GET /api/v1/debt/sustainability as PR #179 serves it at
 * `80f3209` — peer columns renamed to the series they actually measure, the
 * two headline measures kept as declared nulls, and the debt-to-GDP column
 * pinned to one reference year with each row stating whether it is on it.
 */

import type {
  DebtSustainabilityResponse,
  RegionalPeer,
} from '@/lib/api/debt';

/**
 * The post-#179 payload. The annotation is the assertion: this file does not
 * compile if the interface no longer describes it.
 */
const LIVE: DebtSustainabilityResponse = {
  status: 'success',
  debt_to_gdp: {
    value: 70.0,
    year: 2025,
    basis:
      'Central government debt / nominal GDP (CBK debt timeline) — not the IMF general-government measure',
    source: 'CBK Annual Reports / National Treasury BPS',
  },
  debt_service_to_revenue: {
    value: 77.6,
    year: 'FY 2026/27',
  },
  external_debt_share: 44.4,
  projections: [
    { year: 2026, projected_debt_to_gdp: 71.6, is_published_projection: true },
    { year: 2027, projected_debt_to_gdp: 72.4, is_published_projection: true },
  ],
  projections_source: 'IMF World Economic Outlook (GGXWDG_NGDP)',
  projections_absent_reason: null,
  regional_peers: [
    {
      country: 'Kenya',
      debt_to_gdp: 70.0,
      debt_to_gdp_year: 2025,
      debt_service_to_revenue: null,
      debt_service_to_revenue_absent_reason:
        'no_comparable_total_debt_service_series_for_peers',
      external_debt_share: null,
      external_debt_share_absent_reason:
        'no_comparable_share_of_total_public_debt_series_for_peers',
      interest_payments_pct_revenue: 24.3,
      external_debt_pct_gni: 35.0,
    },
    {
      country: 'Rwanda',
      debt_to_gdp: 71.3,
      debt_to_gdp_year: 2025,
      debt_service_to_revenue: null,
      external_debt_share: null,
      interest_payments_pct_revenue: null,
      external_debt_pct_gni: 93.9,
    },
    {
      // No IMF observation at the reference year. Another measure cannot fill it.
      country: 'Ethiopia',
      debt_to_gdp: null,
      debt_to_gdp_year: null,
      debt_to_gdp_absent_reason: 'no_observation',
      debt_to_gdp_source: null,
      debt_service_to_revenue: null,
      external_debt_share: null,
      interest_payments_pct_revenue: null,
      external_debt_pct_gni: null,
    },
    {
      country: 'Tanzania',
      debt_to_gdp: null,
      debt_to_gdp_year: null,
      debt_service_to_revenue: null,
      external_debt_share: null,
      interest_payments_pct_revenue: null,
      external_debt_pct_gni: null,
    },
  ],
  regional_peers_basis: {
    debt_to_gdp: {
      measure: 'General government gross debt, % of GDP',
      indicator: 'GGXWDG_NGDP',
      publisher: 'IMF World Economic Outlook',
      reference_year: 2025,
    },
    interest_payments_pct_revenue: {
      measure: 'Interest payments, % of revenue (excludes principal)',
      indicator: 'GC.XPN.INTP.RV.ZS',
      publisher: 'World Bank',
    },
    external_debt_pct_gni: {
      measure: 'External debt stocks, % of GNI (denominator is GNI, not debt)',
      indicator: 'DT.DOD.DECT.GN.ZS',
      publisher: 'World Bank',
    },
  },
  currency: 'KES',
  source: 'National Treasury BPS, CBK Annual Reports',
};

/** The no-data branch, which returns the same keys with nothing in them. */
const NO_DATA: DebtSustainabilityResponse = {
  status: 'no_data',
  debt_to_gdp: null,
  debt_service_to_revenue: null,
  external_debt_share: null,
  projections: [],
  projections_source: null,
  projections_absent_reason: 'no_published_projection_seeded',
  regional_peers: ['Kenya', 'Ethiopia', 'Tanzania', 'Uganda', 'Rwanda'].map((country) => ({
    country,
    debt_to_gdp: null,
    debt_to_gdp_year: null,
    debt_to_gdp_absent_reason: 'no_reference_year' as const,
    debt_to_gdp_source: null,
    debt_service_to_revenue: null,
    external_debt_share: null,
    interest_payments_pct_revenue: null,
    interest_payments_pct_revenue_year: null,
    interest_payments_pct_revenue_absent_reason: 'no_observation' as const,
    interest_payments_pct_revenue_source: null,
    external_debt_pct_gni: null,
    external_debt_pct_gni_year: null,
    external_debt_pct_gni_absent_reason: 'no_observation' as const,
    external_debt_pct_gni_source: null,
  })),
  // `_peer_column_basis(None)` still names every column; the pinned one just
  // has no year to pin to.
  regional_peers_basis: {
    debt_to_gdp: {
      measure: 'General government gross debt, % of GDP',
      indicator: 'GGXWDG_NGDP',
      publisher: 'IMF World Economic Outlook',
      reference_year: null,
    },
  },
};

/** The non-debt-to-GDP half of a peer row, for shape assertions below. */
const BARE = {
  country: 'Testland',
  debt_service_to_revenue: null,
  external_debt_share: null,
  interest_payments_pct_revenue: null,
  external_debt_pct_gni: null,
} as const;

describe('DebtSustainabilityResponse describes the real payload', () => {
  it('carries measured ratios without unsupported thresholds', () => {
    // Not bare numbers. A consumer that renders `debt_to_gdp` directly would
    // print "[object Object]" — which is what the old type invited.
    expect(LIVE.debt_to_gdp?.value).toBe(70.0);
    expect(LIVE.debt_to_gdp).not.toHaveProperty('threshold_imf');
    expect(LIVE.debt_service_to_revenue).not.toHaveProperty('threshold');
  });

  it('accepts a fiscal-year label where the year is not a calendar year', () => {
    expect(LIVE.debt_service_to_revenue?.year).toBe('FY 2026/27');
  });

  it('names a projection row projected_debt_to_gdp, as the API does', () => {
    expect(LIVE.projections[0].projected_debt_to_gdp).toBe(71.6);
    expect(LIVE.projections.every((p) => p.is_published_projection)).toBe(true);
  });

  it('allows an empty projection list with a stated reason', () => {
    expect(NO_DATA.projections).toEqual([]);
    expect(NO_DATA.projections_absent_reason).toBe('no_published_projection_seeded');
  });
});

describe('regional peers — the two renamed columns', () => {
  it('holds the real series under the names of what they measure', () => {
    const kenya = LIVE.regional_peers[0];
    expect(kenya.interest_payments_pct_revenue).toBe(24.3);
    expect(kenya.external_debt_pct_gni).toBe(35.0);
  });

  it('keeps the headline measures present but null, with a reason', () => {
    const kenya = LIVE.regional_peers[0];
    // Kept rather than dropped so a caller reads a stated absence, not
    // `undefined` — and typed `null`, not `number | null`, so no consumer can
    // put 24.3 back under a label that means total debt service.
    expect(kenya.debt_service_to_revenue).toBeNull();
    expect(kenya.external_debt_share).toBeNull();
    expect(kenya.debt_service_to_revenue_absent_reason).toMatch(/no_comparable/);
  });

  it('lets a peer be missing a column without falling back to a number', () => {
    const rwanda = LIVE.regional_peers[1];
    expect(rwanda.interest_payments_pct_revenue).toBeNull();
    // 93.9% of GNI, not 93.9% of Rwanda's debt held externally. The column
    // name now says which, which is the whole point of the rename.
    expect(rwanda.external_debt_pct_gni).toBe(93.9);
  });

  it('publishes what each column measures alongside the data', () => {
    const basis = LIVE.regional_peers_basis!;
    expect(basis.interest_payments_pct_revenue.indicator).toBe('GC.XPN.INTP.RV.ZS');
    expect(basis.interest_payments_pct_revenue.measure).toMatch(/excludes principal/i);
    expect(basis.external_debt_pct_gni.measure).toMatch(/GNI, not debt/i);
  });

  it('covers every numeric peer column with a basis entry', () => {
    // A column with no stated basis is how three measures came to share one
    // label. Any new column must arrive with one.
    const basis = LIVE.regional_peers_basis!;
    const numericColumns: (keyof RegionalPeer)[] = [
      'debt_to_gdp',
      'interest_payments_pct_revenue',
      'external_debt_pct_gni',
    ];
    for (const col of numericColumns) {
      expect(Object.keys(basis)).toContain(col);
    }
  });
});

/**
 * The debt-to-GDP column and its vintage.
 *
 * `_imf_fetch_debt_to_gdp` asked the DataMapper for five countries over
 * 2018-2026 and took `max(year)`. The DataMapper honours neither filter, so
 * the column was showing each country's 2031 forecast under a present-tense
 * label — Ethiopia at 27.0 against an actual 43.1. Nothing on the page could
 * have revealed that, because no row said which year it was on.
 *
 * The column is pinned to one reference year. Missing observations remain
 * absent with a reason rather than a substitute on another measure or year.
 */
describe('regional peers — debt-to-GDP carries its vintage', () => {
  it('stamps the year on rows that are on the reference year', () => {
    const [kenya, rwanda] = LIVE.regional_peers;
    expect(kenya.debt_to_gdp_year).toBe(2025);
    expect(rwanda.debt_to_gdp_year).toBe(2025);
    expect(LIVE.regional_peers_basis!.debt_to_gdp.reference_year).toBe(2025);
  });

  it('leaves a missing observation absent with its reason', () => {
    const ethiopia = LIVE.regional_peers[2];
    expect(ethiopia.debt_to_gdp).toBeNull();
    expect(ethiopia.debt_to_gdp_absent_reason).toBe('no_observation');
    expect(ethiopia.debt_to_gdp_source).toBeNull();
    expect(ethiopia.debt_to_gdp_year).toBeNull();
  });

  it('lets a country have no debt-to-GDP figure at all', () => {
    const tanzania = LIVE.regional_peers[3];
    expect(tanzania.debt_to_gdp).toBeNull();
    expect(tanzania.debt_to_gdp_year).toBeNull();
  });

  it('makes an unpinned cell distinguishable from a pinned one', () => {
    const ref = LIVE.regional_peers_basis!.debt_to_gdp.reference_year;
    const comparable = LIVE.regional_peers.filter(
      (p) => p.debt_to_gdp !== null && p.debt_to_gdp_year === ref,
    );
    const notComparable = LIVE.regional_peers.filter(
      (p) => p.debt_to_gdp !== null && p.debt_to_gdp_year !== ref,
    );
    expect(comparable.map((p) => p.country)).toEqual(['Kenya', 'Rwanda']);
    expect(notComparable.map((p) => p.country)).toEqual([]);
  });

  it('carries reference_year only on the column that is pinned', () => {
    const basis = LIVE.regional_peers_basis!;
    expect(basis.debt_to_gdp.reference_year).toBe(2025);
    // The World Bank columns are each on their own latest observation; there
    // is no single year to state, so the key is absent rather than guessed.
    expect(basis.interest_payments_pct_revenue.reference_year).toBeUndefined();
    expect(basis.external_debt_pct_gni.reference_year).toBeUndefined();
  });

  it('states a null reference year when none could be established', () => {
    // No WEO table seeded: the IMF fetch is skipped entirely rather than
    // issuing the unbounded call that returned the 2031 projection.
    expect(NO_DATA.regional_peers_basis!.debt_to_gdp.reference_year).toBeNull();
    expect(NO_DATA.regional_peers.every((row) => row.debt_to_gdp === null &&
      row.debt_to_gdp_absent_reason === 'no_reference_year')).toBe(true);
  });
});

describe('regional peers — the type forbids a vintage with no value', () => {
  it('accepts every shape the endpoint actually produces', () => {
    const rows: RegionalPeer[] = [
      { ...BARE, debt_to_gdp: 70.0, debt_to_gdp_year: 2025 },
      { ...BARE, debt_to_gdp: null, debt_to_gdp_year: null },
    ];
    expect(rows).toHaveLength(2);
  });

  it('rejects a year stamped on a cell with no figure', () => {
    // @ts-expect-error — `{debt_to_gdp: null, debt_to_gdp_year: 2025}` claims a
    // vintage for a number that does not exist. If this ever compiles, the
    // union has been flattened and the invariant is gone.
    const impossible: RegionalPeer = { ...BARE, debt_to_gdp: null, debt_to_gdp_year: 2025 };
    expect(impossible).toBeDefined();
  });

  it('rejects a debt figure without a comparable observation year', () => {
    // @ts-expect-error — unsupported legacy fallback shape.
    const unsupported: RegionalPeer = { ...BARE, debt_to_gdp: 43.1, debt_to_gdp_year: null };
    expect(unsupported).toBeDefined();
  });

  it('keeps a sourced zero distinct from absence', () => {
    const zero: RegionalPeer = { ...BARE, debt_to_gdp: 0, debt_to_gdp_year: 2025,
      debt_to_gdp_absent_reason: null,
      debt_to_gdp_source: { publisher: 'IMF World Economic Outlook', indicator: 'GGXWDG_NGDP',
        url: 'https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO/KEN', origin: 'provider' } };
    expect(zero.debt_to_gdp).toBe(0);
    expect(zero.debt_to_gdp_source?.indicator).toBe('GGXWDG_NGDP');
  });

  it('still reads the value without narrowing', () => {
    // The union must not make ordinary consumption awkward, or a caller will
    // reach for `as any` and lose the guarantee.
    const values = LIVE.regional_peers.map((p) => p.debt_to_gdp);
    expect(values).toEqual([70.0, 71.3, null, null]);
  });
});
