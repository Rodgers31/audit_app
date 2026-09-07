/**
 * The External/Domestic split shown beside the headline must be the register's
 * own — or the page must say it is not.
 *
 * `GET /debt/national` answers "how much is external?" twice, and the two
 * disagree by KSh 467.7 billion:
 *
 *   summary.external_debt          5.27T  ← the home card's tile
 *   sum of the external_* categories 4.80T ← what /debt's creditor cards add to
 *
 * The backend computes the second, then overwrites it with the register TOTAL
 * re-split by a proportion from the DebtTimeline table. The parts still sum to
 * the total, so nothing looks wrong — but the tile describes no set of rows the
 * site publishes, and a reader who follows it to /debt finds cards that do not
 * add up to it.
 *
 * Fixtures are the real payload from GET /api/v1/debt/national on 2026-09-06
 * (production, `5ff5fa9`).
 */

import {
  displayedSplit,
  externalShare,
  reconcileExternalDomestic,
  registerSplit,
  summarySplit,
} from '@/lib/debt/externalDomesticSplit';

/** data.categories, 2026-09-06. */
const LIVE_CATEGORIES = {
  external_multilateral: { total_principal: 2_695_722_058_890.222 },
  external_bilateral: { total_principal: 1_087_508_999_335.458 },
  external_commercial: { total_principal: 1_014_147_800_000 },
  domestic_bonds: { total_principal: 5_878_982_400_000 },
  domestic_bills: { total_principal: 1_090_017_800_000 },
  domestic_overdraft: { total_principal: 89_599_800_000 },
  pending_bills: { total_principal: 931_300_000_000 },
};

/** data.summary, same response. */
const LIVE_SUMMARY = {
  external_debt: 5_265_016_798_890.222,
  domestic_debt: 6_590_962_059_335.458,
  external_percentage: 44.4,
  domestic_percentage: 55.6,
};

const REGISTER_EXTERNAL = 4_797_378_858_225.68;
const REGISTER_DOMESTIC = 7_058_600_000_000;
/** The gap the audit measured. */
const GAP = 467_637_940_664.54;

describe('registerSplit', () => {
  it('sums the external and domestic categories — the rows /debt draws', () => {
    const split = registerSplit(LIVE_CATEGORIES)!;
    expect(split.external).toBeCloseTo(REGISTER_EXTERNAL, 0);
    expect(split.domestic).toBeCloseTo(REGISTER_DOMESTIC, 0);
  });

  it('leaves pending bills out of both sides', () => {
    const split = registerSplit(LIVE_CATEGORIES)!;
    expect(split.external + split.domestic).toBeCloseTo(11_855_978_858_225.68, 0);
  });

  it('withholds when only one side exists — a half-known split is not a split', () => {
    expect(registerSplit({ external_multilateral: { total_principal: 1 } })).toBeNull();
    expect(registerSplit({ domestic_bonds: { total_principal: 1 } })).toBeNull();
  });

  it('withholds when a matched category carries no amount', () => {
    expect(
      registerSplit({
        external_multilateral: { total_principal: null, total_outstanding: null },
        domestic_bonds: { total_principal: 1 },
      }),
    ).toBeNull();
  });

  it('withholds on an empty or absent payload', () => {
    expect(registerSplit({})).toBeNull();
    expect(registerSplit(null)).toBeNull();
  });
});

describe('reconcileExternalDomestic — production payload', () => {
  const r = reconcileExternalDomestic(LIVE_CATEGORIES, LIVE_SUMMARY);

  it('finds the two answers in disagreement', () => {
    expect(r.reconciles).toBe(false);
  });

  it('measures the gap the audit reported — KSh 467.7Bn', () => {
    expect(r.gapKes).toBeCloseTo(GAP, 0);
    expect(r.gapKes! / 1e9).toBeCloseTo(467.6, 1);
  });

  it('shows the register split, not the summary, while they disagree', () => {
    const shown = displayedSplit(r)!;
    expect(shown.external).toBeCloseTo(REGISTER_EXTERNAL, 0);
    expect(shown.external).not.toBeCloseTo(LIVE_SUMMARY.external_debt, 0);
  });

  it('renders the share the creditor cards support, not the API percentage', () => {
    // The card printed "44.4% of total" against cards adding to 40.5%.
    expect(externalShare(displayedSplit(r))).toBeCloseTo(40.5, 1);
    expect(externalShare(displayedSplit(r))).not.toBeCloseTo(LIVE_SUMMARY.external_percentage, 1);
  });

  it('keeps the split base equal to the headline total', () => {
    const shown = displayedSplit(r)!;
    expect(shown.external + shown.domestic).toBeCloseTo(11_855_978_858_225.68, 0);
  });
});

describe('reconcileExternalDomestic — when the two agree', () => {
  /** What the payload looks like once the backend stops re-splitting. */
  const FIXED_SUMMARY = { external_debt: REGISTER_EXTERNAL, domestic_debt: REGISTER_DOMESTIC };

  it('reconciles, so the page shows the API figures and drops the disclosure', () => {
    const r = reconcileExternalDomestic(LIVE_CATEGORIES, FIXED_SUMMARY);
    expect(r.reconciles).toBe(true);
    expect(displayedSplit(r)).toEqual(r.summary);
  });

  it('tolerates rounding — a fraction of a percent is not a disagreement', () => {
    const nudged = {
      external_debt: REGISTER_EXTERNAL + 1_000_000_000, // 1Bn on an 11.86T base
      domestic_debt: REGISTER_DOMESTIC - 1_000_000_000,
    };
    expect(reconcileExternalDomestic(LIVE_CATEGORIES, nudged).reconciles).toBe(true);
  });

  it('still catches a gap an order of magnitude below the live one', () => {
    const nudged = {
      external_debt: REGISTER_EXTERNAL + 100_000_000_000, // 100Bn
      domestic_debt: REGISTER_DOMESTIC - 100_000_000_000,
    };
    expect(reconcileExternalDomestic(LIVE_CATEGORIES, nudged).reconciles).toBe(false);
  });
});

describe('reconcileExternalDomestic — absent inputs', () => {
  it('reports no disagreement when there is nothing to compare', () => {
    expect(reconcileExternalDomestic(null, LIVE_SUMMARY).reconciles).toBe(true);
    expect(reconcileExternalDomestic(LIVE_CATEGORIES, null).reconciles).toBe(true);
    expect(reconcileExternalDomestic(null, null).gapKes).toBeNull();
  });

  it('falls back to whichever side exists', () => {
    expect(displayedSplit(reconcileExternalDomestic(null, LIVE_SUMMARY))).toEqual(
      summarySplit(LIVE_SUMMARY),
    );
    expect(displayedSplit(reconcileExternalDomestic(LIVE_CATEGORIES, null))).toEqual(
      registerSplit(LIVE_CATEGORIES),
    );
  });
});

describe('externalShare', () => {
  it('withholds rather than dividing by zero', () => {
    expect(externalShare({ external: 0, domestic: 0 })).toBeNull();
    expect(externalShare(null)).toBeNull();
  });

  it('reports a genuine zero external share as 0, not as absence', () => {
    expect(externalShare({ external: 0, domestic: 100 })).toBe(0);
  });
});
