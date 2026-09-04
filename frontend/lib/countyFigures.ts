/**
 * County money figures — one place that knows which key holds which figure,
 * and that an absent figure stays absent.
 *
 * `County` carries each money figure under two keys for historical reasons
 * (`budget`/`totalBudget`, `debt`/`totalDebt`), and the adapter fills both
 * from the same source. Every consumer used to re-derive the pair inline and
 * end it in `?? 0`, so "the API did not publish this figure" and "the figure
 * is zero" arrived at the UI as the same value. A zero is a claim: that a
 * county was allocated nothing, or owes nothing.
 *
 * These return `undefined` for an absent figure so callers must decide what
 * to say — which is normally "—".
 */
import { County } from '@/types';

/** The county's budget, or `undefined` if the API published none. */
export const countyBudget = (county: County): number | undefined =>
  county.budget ?? county.totalBudget;

/** The county's debt, or `undefined` if the API published none. */
export const countyDebt = (county: County): number | undefined =>
  county.debt ?? county.totalDebt;

/** A total alongside how much of the population it actually covers. */
export interface PublishedSum {
  /** Sum over the counties that published a figure; `null` if none did. */
  total: number | null;
  /** How many counties contributed. */
  reported: number;
  /** How many were asked. */
  of: number;
}

/**
 * Sum a figure across counties, counting only those that published it.
 *
 * Summing absent figures as 0 produces a total that looks complete and is
 * silently short — the failure mode is a headline "total county debt" that
 * quietly omits every county whose loans were never ingested. Callers should
 * surface `reported`/`of` whenever they differ so the total is read for what
 * it is.
 */
export const sumPublished = (
  counties: County[],
  pick: (county: County) => number | undefined
): PublishedSum => {
  let total = 0;
  let reported = 0;
  for (const c of counties) {
    const v = pick(c);
    if (v != null) {
      total += v;
      reported += 1;
    }
  }
  return { total: reported > 0 ? total : null, reported, of: counties.length };
};

/**
 * Order two counties by a published figure, absent ones last.
 *
 * Takes the sort direction rather than returning a value the caller negates.
 * A comparator that returns ±1 for "absent" and is then flipped for a
 * descending sort ranks the absent county FIRST — on a budget column that
 * reads as the largest budget in the country, which is how a county with no
 * published budget came to head the descending ranking table.
 */
export const compareByPublishedFigure = (
  a: County,
  b: County,
  pick: (county: County) => number | undefined,
  dir: 'asc' | 'desc'
): number => {
  const av = pick(a);
  const bv = pick(b);
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  return dir === 'asc' ? av - bv : bv - av;
};
