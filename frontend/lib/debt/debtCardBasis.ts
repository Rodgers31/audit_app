/**
 * Basis rules for the home page's National Debt card.
 *
 * The card draws on two different series and they must not be mixed:
 *
 *   * the headline value is the instrument-register sum from
 *     /api/v1/debt/national, and the API's debt_to_gdp_ratio is the IMF
 *     GENERAL-government measure;
 *   * the timeline behind the chart is the CBK central-government series, and
 *     its own gdpRatio is that total over World Bank GDP.
 *
 * Presenting "69.3%, from 67.8% in 2022" across those two definitions asserts
 * a movement along a single series that does not exist. Extracted here so the
 * rule can be unit-tested rather than living inline in the component.
 */

export interface TimelineBase {
  gdpRatio?: number | null;
  year?: number | string | null;
}

/**
 * The "from X% in YEAR" comparison for the debt-to-GDP stat, or null when the
 * displayed ratio and the available base are on different bases.
 *
 * @param apiGdpRatio the IMF general-government ratio, when the API supplies it
 * @param base        the earliest SOURCED timeline entry
 */
export function gdpRatioComparison(
  apiGdpRatio: number | null | undefined,
  base: TimelineBase | null | undefined,
): { pct: number; year: number | string } | null {
  // The displayed ratio came from the API (IMF basis); the only base we have
  // is the timeline (central government / World Bank GDP). Not comparable.
  if (apiGdpRatio != null) return null;
  if (base?.gdpRatio == null || base.year == null) return null;
  return { pct: base.gdpRatio, year: base.year };
}
