/**
 * The treemap's slice arithmetic (credibility audit F25).
 *
 * On the live site the seven slices summed to 106.9%. `percentage_of_total`
 * comes from the backend divided by a total that EXCLUDES pending bills, while
 * pending bills were rendered as one of the parts — so the pie's parts added
 * up to more than its stated whole, in a chart captioned "TOTAL OWED".
 *
 * The adapter now drops pending bills (they are unpaid obligations, not
 * borrowed money — the backend's own `_is_debt_loan` says so and keeps them
 * out of every debt total) and computes shares over what it actually draws.
 *
 * These tests import the production adapter (lib/debt/lenderTreemapAdapter),
 * which DebtPageClient also uses, so they exercise the shipped path rather than
 * a copy of it. The numbers below are the real ones from GET /debt/national.
 */

import {
  toTreemapCategories as adaptCategories,
  treemapTotal,
  type ApiCategory as AdapterApiCategory,
} from '@/lib/debt/lenderTreemapAdapter';

/** The API shape these fixtures use, plus the backend's own share field. */
type ApiCategory = AdapterApiCategory & { percentage_of_total?: number };

/**
 * Thin wrapper so the existing assertions keep their `{ categories, total }`
 * shape. The transform itself is the SHIPPED one — this file used to
 * reimplement it, so a regression in the page could leave every assertion here
 * green.
 */
function toTreemapCategories(categories: Record<string, ApiCategory>) {
  const adapted = adaptCategories(categories);
  return { categories: adapted, total: treemapTotal(adapted) };
}

// GET /api/v1/debt/national, 2026-09-03.
const LIVE: Record<string, ApiCategory> = {
  domestic_bonds: { total_outstanding: 5_878_982_400_000, percentage_of_total: 43.29 },
  external_multilateral: { total_outstanding: 2_838_182_064_464, percentage_of_total: 20.96 },
  external_commercial: { total_outstanding: 2_676_000_000_000, percentage_of_total: 19.7 },
  domestic_bills: { total_outstanding: 1_090_017_800_000, percentage_of_total: 8.03 },
  external_bilateral: { total_outstanding: 980_000_000_000, percentage_of_total: 7.36 },
  pending_bills: { total_outstanding: 931_300_000_000, percentage_of_total: 6.86 },
  domestic_overdraft: { total_outstanding: 89_651_700_000, percentage_of_total: 0.66 },
};

describe('treemap slice arithmetic', () => {
  it('reproduces the defect from the API figures', () => {
    // What the page did: render every category, using the backend's share.
    const sum = Object.values(LIVE).reduce((s, c) => s + (c.percentage_of_total as number), 0);
    expect(sum).toBeCloseTo(106.86, 2);
    expect(sum).toBeGreaterThan(100);
  });

  it('slices now sum to 100%', () => {
    const { categories } = toTreemapCategories(LIVE);
    const sum = categories.reduce((s, c) => s + c.share, 0);
    expect(sum).toBeCloseTo(100, 6);
  });

  it('excludes pending bills, which are not borrowed money', () => {
    const { categories, total } = toTreemapCategories(LIVE);
    expect(categories.map((c) => c.category)).not.toContain('pending_bills');
    // The stated whole is the sum of what is drawn, not a total that
    // silently contains something the chart omits.
    expect(total).toBeCloseTo(
      categories.reduce((s, c) => s + c.outstanding, 0),
      6
    );
    // This is `total_outstanding` from the API, which already excludes
    // pending bills. That was the shape of the defect: the denominator was
    // right all along, and pending bills were added as a SLICE against it.
    expect(total).toBeCloseTo(13_552_833_964_464, 0);
    expect(total).toBe(
      Object.entries(LIVE)
        .filter(([k]) => !k.includes('pending'))
        .reduce((s, [, c]) => s + Number(c.total_outstanding), 0)
    );
  });

  it('drops empty categories without disturbing the shares', () => {
    const withEmpty = { ...LIVE, domestic_legacy: { total_outstanding: 0, percentage_of_total: 0 } };
    const { categories } = toTreemapCategories(withEmpty);
    expect(categories.map((c) => c.category)).not.toContain('domestic_legacy');
    expect(categories.reduce((s, c) => s + c.share, 0)).toBeCloseTo(100, 6);
  });

  it('still sums to 100% with 42 creditors across three external categories', () => {
    // What the IDS creditor pull produces: many named lenders inside the same
    // categories. The category shares must not care how many lenders there are.
    const many: Record<string, ApiCategory> = {
      external_multilateral: {
        total_outstanding: 2_599_000_000_000,
        percentage_of_total: 0,
        items: Array.from({ length: 13 }, (_, i) => ({
          lender: `Multilateral ${i}`,
          outstanding: 2_599_000_000_000 / 13,
        })),
      },
      external_bilateral: {
        total_outstanding: 1_048_000_000_000,
        percentage_of_total: 0,
        items: Array.from({ length: 17 }, (_, i) => ({
          lender: `Bilateral ${i}`,
          outstanding: 1_048_000_000_000 / 17,
        })),
      },
      external_commercial: {
        total_outstanding: 978_000_000_000,
        percentage_of_total: 0,
        items: Array.from({ length: 12 }, (_, i) => ({
          lender: `Commercial ${i}`,
          outstanding: 978_000_000_000 / 12,
        })),
      },
      domestic_bonds: { total_outstanding: 5_878_982_400_000, percentage_of_total: 0 },
    };
    const { categories } = toTreemapCategories(many);
    expect(categories.reduce((s, c) => s + c.share, 0)).toBeCloseTo(100, 6);
    const creditorCount = categories.reduce((s, c) => s + c.lenders.length, 0);
    expect(creditorCount).toBe(42);
  });

  it('folds the long tail instead of dropping it', () => {
    // The drill-down names 8 and sums the rest. Whatever it shows must still
    // add up to the category, or the panel disagrees with its own header.
    const lenders = Array.from({ length: 17 }, (_, i) => ({
      lender: `Creditor ${i}`,
      outstanding: (17 - i) * 1e10,
    }));
    const NAMED = 8;
    const named = lenders.slice(0, NAMED);
    const tail = lenders.slice(NAMED);
    const tailTotal = tail.reduce((s, l) => s + l.outstanding, 0);

    expect(tail.length).toBe(9);
    expect(
      named.reduce((s, l) => s + l.outstanding, 0) + tailTotal
    ).toBeCloseTo(lenders.reduce((s, l) => s + l.outstanding, 0), 6);
  });
});

describe('the API response the treemap actually receives', () => {
  /**
   * /api/v1/debt/national returns the largest 8 lenders per category plus an
   * explicit remainder — it does not return all 42. Earlier fixtures here
   * listed every creditor, so the long-tail cases passed against a response
   * shape the backend cannot produce.
   */
  const TRUNCATED: Record<string, ApiCategory> = {
    external_multilateral: {
      total_outstanding: 2_599_000_000_000,
      // 8 named, 5 folded away by the API.
      items: Array.from({ length: 8 }, (_, i) => ({
        lender: `Multilateral ${i}`,
        outstanding: 250_000_000_000,
      })),
      items_truncated: true,
      other_lender_count: 5,
      other_outstanding: 599_000_000_000,
    },
    domestic_bonds: { total_outstanding: 5_878_982_400_000 },
  };

  it('keeps the remainder so a category can still account for itself', () => {
    const { categories } = toTreemapCategories(TRUNCATED);
    const multilateral = categories.find((c) => c.category === 'external_multilateral')!;

    expect(multilateral.lenders).toHaveLength(8);
    expect(multilateral.otherLenderCount).toBe(5);

    const named = multilateral.lenders.reduce((s, l) => s + l.outstanding, 0);
    expect(named).toBeLessThan(multilateral.outstanding);
    // Named + folded remainder must reconstruct the category total, or the
    // drill-down disagrees with the header printed above it.
    expect(named + multilateral.otherOutstanding).toBeCloseTo(
      multilateral.outstanding,
      0
    );
  });

  it('shares still sum to 100% on a truncated response', () => {
    const { categories } = toTreemapCategories(TRUNCATED);
    expect(categories.reduce((s, c) => s + c.share, 0)).toBeCloseTo(100, 6);
  });

  it('a category with no remainder reports none', () => {
    const { categories } = toTreemapCategories({
      domestic_bonds: {
        total_outstanding: 300,
        items: [{ lender: 'A', outstanding: 200 }, { lender: 'B', outstanding: 100 }],
      },
    });
    expect(categories[0].otherLenderCount).toBe(0);
    expect(categories[0].otherOutstanding).toBe(0);
  });
});
