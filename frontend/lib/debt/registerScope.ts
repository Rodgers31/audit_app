/**
 * Which rows a published debt figure was actually summed over.
 *
 * `GET /debt/national` returns `loan_count` = `len(loans)` — EVERY national
 * loan row. It also returns `total_outstanding`, which the backend sums with
 * `_is_debt_loan`, a predicate that drops the PENDING_BILLS rows (unpaid
 * invoices are not borrowed money). In production those are 60 and 47
 * respectively, so the hero's "Sum of our instrument register (60 rows)"
 * attributed an 11.86T figure to 13 rows that are not in it.
 *
 * The count is recoverable without a backend change: `categories` carries a
 * per-category `loan_count`, and every debt row lands in exactly one non-
 * pending category. This module does that sum — but only states a number when
 * those same categories add back up to the figure the count is labelling.
 * A count is a claim about a set; if the set does not reconcile with the
 * total, we do not know what was summed and say nothing rather than something
 * plausible.
 *
 * Naming note: this deliberately does NOT call the loans table "the instrument
 * register". There is a separate `debt_instruments` table — the maturity and
 * coupon profile behind /debt's ladder — which the seeding domain documents as
 * covering "~60% of the published bond stock, so a row here must not reach any
 * code that sums a debt total". Two different tables cannot share one name on
 * a page whose whole claim is traceability.
 */

export interface RegisterCategory {
  loan_count?: number | null;
  total_principal?: number | string | null;
  total_outstanding?: number | string | null;
}

export type RegisterCategories = Record<string, RegisterCategory> | null | undefined;

/**
 * Relative tolerance for "the categories add up to the published total".
 *
 * The two are the same sum over the same rows, so they agree exactly in
 * practice; this only absorbs float drift. It is deliberately tight — a wide
 * band here would wave through exactly the kind of missing-category error the
 * check exists to catch.
 */
const RECONCILE_TOLERANCE = 0.001; // 0.1%

/**
 * Categories whose rows are NOT summed into a debt total.
 *
 * Mirrors the backend's `_is_debt_loan`: PENDING_BILLS only. Matching on the
 * category KEY rather than a hardcoded list means a future category is
 * included by default — the fail-safe direction, since omitting a real debt
 * category would break the reconciliation below and withhold the count, rather
 * than quietly under-report it.
 */
export function isDebtCategory(key: string): boolean {
  return !/pending/i.test(key);
}

function asNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * The number of rows behind a published debt total, or `null` when that cannot
 * be established from the payload.
 *
 * `null` is returned — and the caller must then state no count at all — when:
 *   • `categories` is missing or has no debt categories;
 *   • any debt category omits `loan_count` (the sum would be an undercount);
 *   • the debt categories do not add up to `publishedTotal` (the count would
 *     describe a different set from the figure beside it).
 */
export function summedRegisterRows(
  categories: RegisterCategories,
  publishedTotal: number | null | undefined,
): number | null {
  const entries = Object.entries(categories ?? {}).filter(([key]) => isDebtCategory(key));
  if (entries.length === 0) return null;

  let rows = 0;
  let outstanding = 0;
  for (const [, cat] of entries) {
    const count = asNumber(cat?.loan_count);
    if (count === null) return null;
    rows += count;
    // The category's own total, on whichever basis it publishes. Both are
    // present in production and identical; `??` (not `||`) so a genuine
    // zero-value category still reconciles instead of falling through.
    const amount = asNumber(cat?.total_outstanding) ?? asNumber(cat?.total_principal);
    if (amount === null) return null;
    outstanding += amount;
  }

  const total = asNumber(publishedTotal);
  if (total === null || total <= 0) return null;
  if (Math.abs(outstanding - total) / total > RECONCILE_TOLERANCE) return null;

  return rows;
}

/**
 * The source line under the headline total.
 *
 * Names the table (`loans`, not "instrument register"), the row count when it
 * reconciles, and the exclusion that makes the count differ from the API's
 * `loan_count`. With no reconcilable count it still names the table and the
 * exclusion — both are true regardless — and simply omits the number.
 */
export function registerSourceLabel(rows: number | null): string {
  return rows == null
    ? 'Sum of our loans table, excluding pending bills'
    : `Sum of ${rows} loan rows — pending bills excluded`;
}
