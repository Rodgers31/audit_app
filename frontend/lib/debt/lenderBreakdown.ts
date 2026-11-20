/**
 * Adapt the named creditors and published remainder from /debt/national.
 * Supplier bills belong in Stalled payments. Group shares use the total of
 * the positive lender categories shown, which excludes those bills.
 */

import { displayLenderName } from './lenderName';
import { isDebtCategory } from './registerScope';

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

type AmountBasis = 'outstanding' | 'principal';

export interface LenderAmount {
  outstanding: number | null;
  basis: AmountBasis;
}

export interface LenderCategory {
  category: string;
  label: string;
  outstanding: number;
  basis: AmountBasis;
  share: number;
  lenders: Array<LenderAmount & { lender: string }>;
  otherLenderCount: number;
  otherOutstanding: number | null;
  itemsTruncated: boolean;
}

function amount(value: number | string | null | undefined): number | null {
  if (typeof value !== 'number' && (typeof value !== 'string' || !value.trim())) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function labelFor(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

export function toLenderCategories(
  categories: Record<string, ApiCategory> | null | undefined,
): LenderCategory[] {
  const drawn = Object.entries(categories ?? {}).flatMap(([key, category]) => {
    if (!isDebtCategory(key)) return [];
    const outstanding = amount(category.total_outstanding ?? category.total_principal);
    if (outstanding == null || outstanding === 0) return [];
    const otherLenderCount = category.other_lender_count;
    const count = typeof otherLenderCount === 'number' && Number.isInteger(otherLenderCount) && otherLenderCount > 0
      ? otherLenderCount : 0;
    const otherOutstanding = amount(category.other_outstanding);
    const itemsTruncated = category.items_truncated === true || count > 0 ||
      (otherOutstanding != null && otherOutstanding > 0);
    return [{
      category: key,
      label: labelFor(key),
      outstanding,
      basis: category.total_outstanding == null ? 'principal' as const : 'outstanding' as const,
      lenders: (category.items ?? []).map(item => ({
        lender: displayLenderName(item.lender),
        outstanding: amount(item.outstanding ?? item.principal),
        basis: item.outstanding == null ? 'principal' as const : 'outstanding' as const,
      })),
      otherLenderCount: count,
      otherOutstanding: itemsTruncated ? otherOutstanding : 0,
      itemsTruncated,
    }];
  });

  const total = lenderCategoryTotal(drawn);
  return drawn.map(category => ({ ...category, share: category.outstanding / total * 100 }));
}

export function lenderCategoryTotal(categories: ReadonlyArray<{ outstanding: number }>): number {
  return categories.reduce((sum, category) => sum + category.outstanding, 0);
}

export function formatLenderShare(share: number): string {
  if (share > 0 && share < 0.1) return '<0.1';
  const whole = Math.round(share);
  if (whole === 0 || (whole === 100 && share < 100) || (whole === 50 && share !== 50)) {
    const precise = share.toFixed(2).replace(/\.?0+$/, '');
    if (precise === '100' || precise === '50') return `${share < whole ? '<' : '>'}${whole}`;
    return precise;
  }
  return String(whole);
}
