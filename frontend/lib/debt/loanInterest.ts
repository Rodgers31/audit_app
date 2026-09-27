/**
 * How a register row's rate and annual cost are shown.
 *
 * Until issue #235 the loans API sent `"0.00%"` and `0` for 45 of 48 rows —
 * the writer stored a zero where no publisher gave a rate — and the April-2025
 * fixture's 14.5% / 16% for the rest. The homepage card listed fourteen rows
 * reading "0.00%  KES 0" and totalled three fixture rates as the "Annual
 * Service Cost".
 *
 * The API now sends each figure with its basis or with the reason it is
 * absent. This module turns that into what a reader sees, in one place, so
 * the homepage card and the /debt register cannot drift apart:
 *
 *  - absent   → "—", with the reason as the hover text; never 0.
 *  - modelled → the amount, tagged "modelled": balance × a published rate is
 *               arithmetic, not a figure any publisher states.
 *  - published→ the amount, tagged with its period ("paid 2024").
 */
import type { AnnualDebtService, NationalLoan } from '@/lib/api/debt';

export interface FigureCell {
  /** What goes in the cell. `null` means render the absent mark. */
  value: number | null;
  /** Short tag beside the value, e.g. "modelled" or "paid 2024". */
  tag: string | null;
  /** Hover text: the basis label, or why there is no figure. */
  title: string;
}

export function rateCell(loan: NationalLoan): FigureCell {
  if (loan.interest_rate_pct == null) {
    return {
      value: null,
      tag: null,
      title: loan.interest_rate_absent_reason || 'No published rate.',
    };
  }
  return {
    value: loan.interest_rate_pct,
    tag: loan.interest_rate_basis === 'auction_yield' ? '91-day yield' : 'avg coupon',
    title: loan.interest_rate_label || '',
  };
}

export function annualCostCell(loan: NationalLoan): FigureCell {
  if (loan.annual_service_cost == null) {
    return {
      value: null,
      tag: null,
      title: loan.annual_service_absent_reason || 'No published interest figure.',
    };
  }
  const label = loan.annual_service_label || '';
  if (loan.annual_service_basis === 'modelled') {
    return { value: loan.annual_service_cost, tag: 'modelled', title: label };
  }
  // "Interest paid in 2024" → "paid 2024"
  const year = /\b(\d{4})\b/.exec(label)?.[1];
  return {
    value: loan.annual_service_cost,
    tag: year ? `paid ${year}` : 'paid',
    title: label,
  };
}

export type LoanSortKey = 'outstanding' | 'rate' | 'service';

/**
 * Sort descending with ABSENT figures last. The old comparator read an absent
 * rate as 0, which ranks "nobody published this" as "the cheapest loan".
 */
export function sortLoans(loans: NationalLoan[], key: LoanSortKey): NationalLoan[] {
  const pick = (l: NationalLoan): number | null =>
    key === 'rate'
      ? l.interest_rate_pct
      : key === 'service'
        ? l.annual_service_cost
        : l.outstanding_numeric;
  return [...loans].sort((a, b) => {
    const va = pick(a);
    const vb = pick(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return vb - va;
  });
}

/** The homepage card's headline service figure, with what it measures. */
export function annualDebtServiceHeadline(ads: AnnualDebtService | null | undefined): {
  value: number | null;
  period: string | null;
  /** The document the figure is from — says whether it is a budget or an outturn. */
  sourceTitle: string | null;
  title: string;
} {
  if (!ads || ads.value_kes == null) {
    return {
      value: null,
      period: null,
      sourceTitle: null,
      title: ads?.absent_reason || 'No published debt-service figure.',
    };
  }
  const src = ads.source;
  return {
    value: ads.value_kes,
    period: ads.fiscal_year ?? null,
    sourceTitle: src?.title ?? null,
    title: [ads.measure, src ? `Source: ${src.title}${src.page ? `, ${src.page}` : ''}` : null]
      .filter(Boolean)
      .join('. '),
  };
}
