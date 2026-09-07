/**
 * When a pending-bills aging distribution may be drawn as measured.
 *
 * The backend has no aging observation for any bill it currently serves. Both
 * pending-bills endpoints fall back to the loans table, and both then emit a
 * hardcoded shape:
 *
 *   "aging_buckets": {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": total}
 *
 * That is not a measurement of anything. It asserts that 100% of KSh 1.1
 * trillion of unpaid bills — the national figure, and the figure on every one
 * of the 47 county pages — is more than 180 days old, on no evidence. Bills
 * past 180 days go to the Pending Bills Verification Committee, so the chart
 * says something specific and consequential about every shilling in it.
 *
 * The page cannot check the claim, so it must not draw it. This module decides
 * that, and the decision is made on the payload alone so it holds whatever the
 * backend sends — including a backend that keeps emitting the fabricated shape
 * after this ships.
 *
 * Two signals, in order:
 *
 *  1. DECLARED provenance. `data_source` names the table the answer came from.
 *     `loans_table_fallback` and `none` carry no per-bill aging by
 *     construction, so nothing derived from them is measured. This is the
 *     primary test: provenance is declared, not sniffed.
 *  2. SHAPE, as a fail-closed fallback for a payload that declares nothing.
 *     A distribution whose entire mass sits in one bucket is indistinguishable
 *     from the hardcoded shape, so it is not drawn. This withholds the rare
 *     genuine all-one-bucket case; that is the correct direction to err when
 *     the alternative is publishing an invented distribution.
 */

export interface AgingBucket {
  bucket: string;
  amount: number;
  percentage: number;
  count?: number;
}

/** `data_source` values that carry no per-bill detail — no aging, no bill type. */
const SOURCES_WITHOUT_BILL_DETAIL = new Set([
  'loans_table_fallback',
  'none',
  'database_empty',
  'database_unavailable',
]);

/** `data_source` values that do carry per-bill detail. */
const SOURCES_WITH_BILL_DETAIL = new Set(['pending_bills_table']);

/**
 * Whether the payload DECLARES a source carrying bill-level detail.
 *
 * `null` means it declared nothing recognisable — the caller then falls back
 * to the shape test rather than assuming either way.
 */
export function declaresBillLevelDetail(dataSource: unknown): boolean | null {
  if (typeof dataSource !== 'string' || dataSource === '') return null;
  const key = dataSource.trim().toLowerCase();
  if (SOURCES_WITHOUT_BILL_DETAIL.has(key)) return false;
  if (SOURCES_WITH_BILL_DETAIL.has(key)) return true;
  return null;
}

export type AgingUnsupportedReason =
  /** Nothing to draw: no buckets, or every bucket is zero. */
  | 'no-data'
  /** The payload declares a source that carries no aging observation. */
  | 'not-measured'
  /** Every shilling sits in one bucket — the fabricated shape's signature. */
  | 'single-bucket';

export type AgingSupport =
  | { supported: true }
  | { supported: false; reason: AgingUnsupportedReason };

/**
 * The API returns aging as a `{bucket: amount}` object; the charts want rows.
 *
 * Kept here rather than in each component so both surfaces share one shape —
 * and so the guard below cannot be bypassed by a component that normalises on
 * its own. `percentage` is only computed against a positive total; with no
 * total the rows still carry their amounts and the guard withholds the chart.
 */
export function normalizeAgingBuckets(
  raw: unknown,
  total: number | null | undefined,
): AgingBucket[] {
  const base = typeof total === 'number' && Number.isFinite(total) && total > 0 ? total : null;

  const rows: AgingBucket[] = Array.isArray(raw)
    ? raw.map((b: any) => ({
        bucket: String(b?.bucket ?? ''),
        amount: Number(b?.amount) || 0,
        percentage: Number(b?.percentage) || 0,
        count: b?.count,
      }))
    : raw && typeof raw === 'object'
      ? Object.entries(raw as Record<string, unknown>).map(([bucket, amount]) => ({
          bucket,
          amount: Number(amount) || 0,
          percentage: 0,
        }))
      : [];

  return rows.map((r) => ({
    ...r,
    percentage: r.percentage || (base ? (r.amount / base) * 100 : 0),
  }));
}

export interface AgingPayload {
  data_source?: unknown;
  aging_buckets?: unknown;
}

/**
 * Whether an aging distribution may be drawn as measured.
 *
 * `buckets` are the normalised rows; `payload` is the response they came from,
 * read only for its declared `data_source`.
 */
export function agingDistributionSupport(
  buckets: AgingBucket[] | null | undefined,
  payload?: AgingPayload | null,
): AgingSupport {
  const rows = buckets ?? [];
  const withMass = rows.filter((b) => Number.isFinite(b.amount) && b.amount > 0);

  if (withMass.length === 0) return { supported: false, reason: 'no-data' };

  if (declaresBillLevelDetail(payload?.data_source) === false) {
    return { supported: false, reason: 'not-measured' };
  }

  if (withMass.length === 1) return { supported: false, reason: 'single-bucket' };

  return { supported: true };
}

/**
 * What to tell the reader in place of the chart.
 *
 * Says what IS known (the total is real — it comes from the Treasury's Budget
 * Review and Outlook Paper) and what is not, without implying a schedule for
 * fixing it. The previous copy on /debt promised "a richer breakdown will
 * appear once the pending_bills seed lands", which reads as a delivery date
 * for a dataset nobody has committed to publishing.
 */
export function agingUnsupportedNote(reason: AgingUnsupportedReason): string {
  switch (reason) {
    case 'no-data':
      return 'No aging breakdown has been published for these bills.';
    case 'not-measured':
      return 'How long these bills have gone unpaid is not recorded in the source they come from, so no age breakdown is shown. The total above is unaffected.';
    case 'single-bucket':
      return 'The source reports every shilling in a single age band, which cannot be told apart from an unmeasured figure, so no age breakdown is shown. The total above is unaffected.';
  }
}
