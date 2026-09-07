/**
 * Reconciling the External / Domestic split against the register it claims to
 * describe.
 *
 * `GET /debt/national` returns TWO answers to "how much of this is external?"
 * and they disagree by KSh 467.7 billion:
 *
 *   summary.external_debt      5.27T   ← rendered on the home debt card
 *   sum of external_* categories 4.80T ← what /debt's creditor cards add to
 *
 * They disagree because `summary` is not a sum of anything on the page. The
 * backend first computes the split from the register's own categories, then
 * overwrites it (`main.py`, `external_debt = _base * (_tl_ext / _tl_split)`)
 * with the register TOTAL re-split by a proportion taken from the DebtTimeline
 * table — a different table, on a different date, in a different basis. The
 * parts still sum to the total, so nothing on screen looks wrong; but "KES
 * 5.27T · 44.4% of total" labelled "External debt" describes no set of rows we
 * publish, and a reader who opens /debt to see which creditors make it up
 * finds cards adding to 4.80T.
 *
 * The rule this module enforces is the page's, not the API's: a split shown as
 * the composition of the register must be the register's own. So the caller
 * renders the category-derived figures — the ones the creditor breakdown adds
 * up to — and discloses the API's alternative and the size of the gap. When
 * the backend's own fix lands and the two agree, `reconciles` goes true and
 * the disclosure disappears on its own.
 */

import type { RegisterCategories, RegisterCategory } from './registerScope';

export interface SplitSummary {
  external_debt?: number | string | null;
  domestic_debt?: number | string | null;
}

export interface SplitPair {
  external: number;
  domestic: number;
}

export interface SplitReconciliation {
  /** External/domestic as the register's own category rows add up. */
  register: SplitPair | null;
  /** What the API's `summary` block states. */
  summary: SplitPair | null;
  /** |summary.external − register.external| in KES; equal on the domestic side. */
  gapKes: number | null;
  /**
   * True when the two agree closely enough that the summary can be shown as
   * the register's composition. Also true when only one of the two exists —
   * there is then nothing to contradict.
   */
  reconciles: boolean;
}

/**
 * How far apart the two answers may be before the page stops presenting the
 * API's split as the register's composition.
 *
 * 0.5% of the split base. In production the gap is 3.9% — nearly eight times
 * this — so the disclosure fires; float drift and sub-billion rounding do not.
 */
const SPLIT_TOLERANCE = 0.005;

function asNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function categoryAmount(cat: RegisterCategory | undefined): number | null {
  if (!cat) return null;
  return asNumber(cat.total_principal) ?? asNumber(cat.total_outstanding);
}

/**
 * Sum the register's `external_*` and `domestic_*` categories.
 *
 * Returns `null` unless BOTH sides are present and every category matched
 * carries an amount — a half-known split is not a split, and filling the
 * missing half with zero would publish "0% external" as a finding.
 */
export function registerSplit(categories: RegisterCategories): SplitPair | null {
  const entries = Object.entries(categories ?? {});
  if (entries.length === 0) return null;

  let external: number | null = null;
  let domestic: number | null = null;

  for (const [key, cat] of entries) {
    const side = key.startsWith('external') ? 'external' : key.startsWith('domestic') ? 'domestic' : null;
    if (!side) continue;
    const amount = categoryAmount(cat);
    if (amount === null) return null;
    if (side === 'external') external = (external ?? 0) + amount;
    else domestic = (domestic ?? 0) + amount;
  }

  if (external === null || domestic === null) return null;
  return { external, domestic };
}

/** The `summary` block's split, or `null` when either side is absent. */
export function summarySplit(summary: SplitSummary | null | undefined): SplitPair | null {
  const external = asNumber(summary?.external_debt);
  const domestic = asNumber(summary?.domestic_debt);
  if (external === null || domestic === null) return null;
  return { external, domestic };
}

export function reconcileExternalDomestic(
  categories: RegisterCategories,
  summary: SplitSummary | null | undefined,
): SplitReconciliation {
  const register = registerSplit(categories);
  const apiSummary = summarySplit(summary);

  if (!register || !apiSummary) {
    // Nothing to contradict: one side of the comparison does not exist.
    return { register, summary: apiSummary, gapKes: null, reconciles: true };
  }

  const gapKes = Math.abs(apiSummary.external - register.external);
  const base = register.external + register.domestic;
  const reconciles = base > 0 ? gapKes / base <= SPLIT_TOLERANCE : gapKes === 0;

  return { register, summary: apiSummary, gapKes, reconciles };
}

/**
 * The pair the page should show as the register's composition.
 *
 * When the two agree, either will do and the API's is used unchanged. When
 * they disagree it is the register's own sum — the figure the creditor cards
 * on /debt add up to — because that is the only one of the two that describes
 * a set of rows the site publishes.
 */
export function displayedSplit(r: SplitReconciliation): SplitPair | null {
  if (!r.reconciles && r.register) return r.register;
  return r.summary ?? r.register;
}

/** Share of the split base, or `null` when the split is unknown. */
export function externalShare(split: SplitPair | null): number | null {
  if (!split) return null;
  const base = split.external + split.domestic;
  if (base <= 0) return null;
  return +((split.external / base) * 100).toFixed(1);
}
