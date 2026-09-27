/**
 * Kenya's risk-of-debt-distress rating, as the joint IMF–World Bank Debt
 * Sustainability Analysis (DSA) publishes it.
 *
 * `/api/v1/debt/national` serves it as `data.debt_sustainability.imf_dsa`,
 * declared verbatim in `backend/services/imf_dsa.py` with the document, date
 * and page it is printed on.
 *
 * Issue #269. The homepage used to print "High risk of debt distress · IMF"
 * from a backend `risk_level` that was really `debt_to_gdp > 65`. When that
 * was missing it banded the ratio itself at an uncited 40/60. Neither was the
 * IMF's. This is now the only source of a risk rating on the homepage, and
 * it fails closed: a rating without its URL, page and date is not shown.
 */

export interface ImfDsaRating {
  risk_of_external_debt_distress: string;
  overall_risk_of_debt_distress: string;
  granularity_in_the_risk_rating?: string;
  source: {
    series: string;
    url: string;
    /** ISO date printed on the DSA itself. */
    dsa_date: string;
    published?: string;
    page: number;
    page_label?: string;
  };
  latest_confirmed?: { as_of: string; title?: string; url?: string; row?: number };
  freshness?: { status: 'recent_confirmation' | 'confirmation_aging' | 'unknown'; evaluated_on: string };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** "2024-10-18" → "Oct 2024". Parsed by hand so no timezone can shift the month. */
function monthYear(iso: string): string | null {
  const m = ISO_DATE.exec(iso);
  if (!m) return null;
  const month = MONTHS[Number(m[2]) - 1];
  return month ? `${month} ${m[1]}` : null;
}

/** "2026-03-31" → "31 Mar 2026". */
function dayMonthYear(iso: string): string | null {
  const m = ISO_DATE.exec(iso);
  if (!m) return null;
  const month = MONTHS[Number(m[2]) - 1];
  return month ? `${Number(m[3])} ${month} ${m[1]}` : null;
}

const nonEmpty = (v: unknown): v is string => typeof v === 'string' && v.trim() !== '';

/**
 * The cited rating, or `null`.
 *
 * `null` covers: no `imf_dsa` (for example an older backend that still sends
 * the ratio-derived `risk_level`, which is deliberately ignored), and a rating
 * that has lost its URL, page or date.
 */
export function readDsaRating(debtSustainability: unknown): ImfDsaRating | null {
  if (!debtSustainability || typeof debtSustainability !== 'object') return null;
  const r = (debtSustainability as { imf_dsa?: unknown }).imf_dsa as Partial<ImfDsaRating> | undefined;
  if (!r || typeof r !== 'object') return null;
  const src = r.source;
  if (
    !nonEmpty(r.overall_risk_of_debt_distress) ||
    !nonEmpty(r.risk_of_external_debt_distress) ||
    !src ||
    !nonEmpty(src.url) ||
    !nonEmpty(src.series) ||
    typeof src.page !== 'number' ||
    !Number.isFinite(src.page) ||
    !nonEmpty(src.dsa_date) ||
    monthYear(src.dsa_date) == null
  ) {
    return null;
  }
  return r as ImfDsaRating;
}

/** Link text: "IMF–World Bank DSA, Oct 2024". */
export function dsaSourceLabel(r: ImfDsaRating): string {
  return `IMF–World Bank DSA, ${monthYear(r.source.dsa_date)}`;
}

/** Always visible beside the assessment; a retrieval cannot renew this evidence. */
export function dsaVintageLabel(r: ImfDsaRating): string {
  const published = r.source.published && dayMonthYear(r.source.published);
  const confirmed = r.latest_confirmed?.as_of && dayMonthYear(r.latest_confirmed.as_of);
  return [
    published ? `Published ${published}.` : 'Publication date unavailable.',
    confirmed ? `Latest confirmed by the IMF register as of ${confirmed}.` : 'Latest status unconfirmed.',
    r.freshness?.status === 'recent_confirmation'
      ? 'Dated assessment; current status may differ.'
      : 'Confirmation needs review; current status unverified.',
  ].join(' ');
}

/** Opens the PDF at the page the rating is printed on. */
export function dsaHref(r: ImfDsaRating): string {
  return `${r.source.url}#page=${r.source.page}`;
}

/** The full citation, for a link's title. */
export function dsaCitation(r: ImfDsaRating): string {
  const page = r.source.page_label ?? `PDF p. ${r.source.page}`;
  const parts = [
    `Overall risk of debt distress: ${r.overall_risk_of_debt_distress}; ` +
      `risk of external debt distress: ${r.risk_of_external_debt_distress}.`,
    `${r.source.series}, ${page}. DSA dated ${dayMonthYear(r.source.dsa_date)}.`,
  ];
  const asOf = r.latest_confirmed?.as_of ? dayMonthYear(r.latest_confirmed.as_of) : null;
  if (asOf) parts.push(`Still the IMF’s latest published DSA for Kenya as of ${asOf}.`);
  return parts.join(' ');
}

/** High, or already in distress. These are the two ratings that warrant the alarm styling. */
export function dsaIsAlarm(r: ImfDsaRating | null): boolean {
  if (!r) return false;
  const v = r.overall_risk_of_debt_distress.trim().toLowerCase();
  return v === 'high' || v === 'in debt distress';
}
