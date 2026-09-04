/**
 * Adapter from /api/v1/debt/national's `categories` map to the shape
 * LenderTreemap draws.
 *
 * Extracted out of DebtPageClient so the treemap's own unit tests exercise the
 * SHIPPED path. The tests previously reimplemented this transform, so a
 * regression in the page could leave every assertion green — and the copy did
 * not model the API's truncation, which is why long-tail cases passed that were
 * impossible against the real response.
 *
 * Two rules this encodes:
 *
 *  1. Pending bills are not drawn. They are unpaid obligations, not borrowed
 *     money — the backend's own `_is_debt_loan` keeps them out of every debt
 *     total, and charting them beside Treasury bonds double-counted them
 *     against the page's "Stalled payments" section.
 *  2. Shares are computed over the total of what is ACTUALLY DRAWN, so the
 *     slices sum to 100% rather than to some fraction of a wider total.
 */

export interface ApiLenderItem {
  lender: string;
  outstanding?: number | string | null;
  principal?: number | string | null;
  interest_rate?: number | null;
  annual_service_cost?: number | null;
}

export interface ApiCategory {
  total_outstanding?: number | string | null;
  total_principal?: number | string | null;
  items?: ApiLenderItem[] | null;
  /** Lenders beyond the named ones the API returns. */
  other_lender_count?: number | null;
  other_outstanding?: number | string | null;
  items_truncated?: boolean | null;
}

export interface TreemapLender {
  lender: string;
  outstanding: number;
  rate?: number | null;
  annual_service_cost?: number | null;
}

export interface TreemapCategory {
  category: string;
  label: string;
  outstanding: number;
  share: number;
  lenders: TreemapLender[];
  /** Lenders the API folded away, so the drill-down can account for them. */
  otherLenderCount: number;
  otherOutstanding: number;
}

function labelFor(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function isDrawnCategory(key: string): boolean {
  return !key.includes('pending');
}

export function toTreemapCategories(
  categories: Record<string, ApiCategory> | null | undefined,
): TreemapCategory[] {
  const drawn = Object.entries(categories ?? {})
    .map(([key, val]) => ({
      category: key,
      label: labelFor(key),
      outstanding: Number(val.total_outstanding ?? val.total_principal ?? 0),
      lenders: (val.items ?? []).map((it) => ({
        lender: it.lender,
        outstanding: Number(it.outstanding ?? it.principal ?? 0) || 0,
        rate: it.interest_rate,
        annual_service_cost: it.annual_service_cost,
      })),
      // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- not a published figure: zero means "render no tail", and an API too old to send these fields has no tail to describe
      otherLenderCount: Number(val.other_lender_count ?? 0) || 0,
      // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- same: the tail row is only drawn when this is non-zero, so nothing claims "KES 0 of other creditors"
      otherOutstanding: Number(val.other_outstanding ?? 0) || 0,
    }))
    .filter((c) => c.outstanding > 0 && isDrawnCategory(c.category));

  const drawnTotal = drawn.reduce((sum, c) => sum + c.outstanding, 0);
  return drawn.map((c) => ({
    ...c,
    share: drawnTotal > 0 ? (c.outstanding / drawnTotal) * 100 : 0,
  }));
}

/**
 * The denominator the treemap divides by — the total of what it actually
 * draws, not a wider total that includes categories it omits.
 */
export function treemapTotal(categories: TreemapCategory[]): number {
  return categories.reduce((sum, c) => sum + c.outstanding, 0);
}
