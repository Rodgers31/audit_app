/**
 * MapUtilities – colour helpers, name matching, legend data
 * Uses the gov-* design-token palette for visual consistency.
 */

import { countyBudget, countyDebt } from '@/lib/countyFigures';
import { County } from '@/types';

/* ────────────────── name matching ────────────────── */

export const getCountyByName = (geoCountyName: string, counties: County[]): County | undefined => {
  if (!counties || counties.length === 0) return undefined;

  const normalize = (s: string) =>
    s
      .toLowerCase()
      .replace(/county/g, '')
      .replace(/[^a-z]/g, '')
      .trim();

  const aliases: Record<string, string> = {
    elgeyomarakwet: 'elgeyomarakwet',
    thika: 'kiambu',
    eldoret: 'uasingishu',
    mombasa: 'mombasa',
    nairobi: 'nairobi',
  };

  const normalizedGeoName = aliases[normalize(geoCountyName)] || normalize(geoCountyName);

  return counties.find((c) => {
    const n = normalize(c.name);
    return (
      n === normalizedGeoName || normalizedGeoName.includes(n) || n.includes(normalizedGeoName)
    );
  });
};

/* ────────────────── audit colour palette (gov tokens) ────────────────── */

const AUDIT_PALETTE: Record<
  string,
  { base: string; hover: string; active: string; muted: string }
> = {
  // Greens — gov-sage / gov-forest (richer bases so good counties read as a
  // confident green at a glance, not a washed-out pale wash)
  clean: { base: '#4A7C5C', hover: '#3d6a4e', active: '#1B3A2A', muted: '#b5d4bf' },
  'A+': { base: '#2f5940', hover: '#244632', active: '#1B3A2A', muted: '#a6ccb4' },
  A: { base: '#3d6a4e', hover: '#2f5940', active: '#1B3A2A', muted: '#b5d4bf' },
  'A-': { base: '#4f8a62', hover: '#427552', active: '#2f5940', muted: '#c4dec9' },
  // Yellows — gov-gold
  qualified: { base: '#D9A441', hover: '#c49338', active: '#a87a24', muted: '#edd5a2' },
  'B+': { base: '#89a851', hover: '#6f8e40', active: '#557430', muted: '#c8daa5' },
  B: { base: '#D9A441', hover: '#c49338', active: '#a87a24', muted: '#edd5a2' },
  'B-': { base: '#d48c32', hover: '#be7928', active: '#a0651e', muted: '#ecc89a' },
  // Reds — gov-copper
  adverse: { base: '#C94A4A', hover: '#b03d3d', active: '#8f2e2e', muted: '#e8b3b3' },
  C: { base: '#C94A4A', hover: '#b03d3d', active: '#8f2e2e', muted: '#e8b3b3' },
  'C+': { base: '#d46545', hover: '#c0563a', active: '#a84730', muted: '#ecc1b3' },
  D: { base: '#8f2e2e', hover: '#7a2525', active: '#651c1c', muted: '#daa4a4' },
  // Violet
  disclaimer: { base: '#7c5cbf', hover: '#6a4aad', active: '#573d94', muted: '#c4b5e0' },
  // Cool slate — counties whose OAG audit hasn't been ingested yet.
  // Production currently has audit_status="pending" for all counties;
  // without this entry they silently hit FALLBACK_PAL and the map's
  // audit legend looked like a styling accident instead of a data gap.
  pending: { base: '#c3cdd5', hover: '#a9b6c0', active: '#7f909d', muted: '#dfe5ea' },
};

const FALLBACK_PAL = { base: '#b0b6ba', hover: '#979ea3', active: '#6b7280', muted: '#d5d8db' };

/** Softer fill for counties with no matching data */
const UNMATCHED_FILL = '#dce1dd';

/* ────────────────── county fill colour ────────────────── */

const paletteFor = (county: County) => {
  const key = county.auditStatus ?? county.audit_rating ?? 'B';
  return AUDIT_PALETTE[key] || FALLBACK_PAL;
};

/** Visual state a county can be in, resolved by the caller. */
export interface CountyFillState {
  isSelected: boolean;
  /** Auto-rotate target while nothing is selected or hovered. */
  isAutoActive: boolean;
  isHovered: boolean;
  visualMode: 'focus' | 'overview';
}

/**
 * Fill colour for an already-resolved county. Takes the County object
 * (not the geo name) so callers can resolve name→county once per data
 * change instead of re-running the regex-normalising linear scan in
 * getCountyByName for all 47 geographies on every render.
 */
export const getCountyFill = (county: County | undefined, state: CountyFillState): string => {
  if (!county) return UNMATCHED_FILL;
  const pal = paletteFor(county);

  // Selected or auto-rotating county — deepest shade. Hover anywhere
  // suppresses the auto-rotate shade (caller clears isAutoActive) so we
  // never have two counties reading as "active" at once.
  if (state.isSelected || state.isAutoActive) return pal.active;

  // Hovered county — mid shade
  if (state.isHovered) return pal.hover;

  // Focus mode — muted tint for non-active
  if (state.visualMode === 'focus') return pal.muted;

  // Overview mode — base audit colour
  return pal.base;
};

/** Hover fill for an already-resolved county (used in Geography hover style) */
export const getCountyHoverFill = (county: County | undefined): string =>
  county ? paletteFor(county).hover : '#c8cec9';

/* ────────────────── helpers ────────────────── */

/**
 * Debt as a percentage of budget, or `null` when either figure is absent.
 *
 * Withholding is the point. `(county.debt || 0) / county.budget` reported a
 * confident "0.0%" for a county whose debt the API never published, which
 * reads as "this county owes nothing" — a claim the source never made. A
 * caller that cannot render "—" should not call this at all.
 *
 * A genuine 0 debt against a published budget still returns 0: that is a
 * figure, not an absence.
 */
export const countyDebtRatio = (county: County): number | null => {
  const debt = countyDebt(county);
  const budget = countyBudget(county);
  if (debt == null || budget == null || budget <= 0) return null;
  return (debt / budget) * 100;
};

/**
 * Budget minus what the county received, or `null` when either is absent.
 *
 * The tooltip renders a "Funding gap" alert whenever this is positive, so an
 * absent `moneyReceived` treated as 0 accused every such county of having
 * received none of its entire budget. The subtraction is only meaningful when
 * both sides were actually published.
 */
export const countyFundingGap = (county: County): number | null => {
  const budget = countyBudget(county);
  const received = county.moneyReceived;
  if (budget == null || received == null) return null;
  return budget - received;
};

export const getFinancialTrend = (
  county: County
): 'excellent' | 'good' | 'fair' | 'poor' | 'unknown' => {
  const utilization = county.budgetUtilization;
  const debtRatio = countyDebtRatio(county);

  // A trend is a judgement about a county, so it needs both inputs to have
  // been published. Grading on figures nobody reported put counties in a
  // bucket they had not earned in either direction: an absent execution rate
  // read as 0% and sank the county to "poor", while an absent debt figure
  // read as debt-free and lifted it to "excellent".
  if (utilization == null || debtRatio == null) return 'unknown';

  if (utilization > 90 && debtRatio < 30) return 'excellent';
  if (utilization > 80 && debtRatio < 50) return 'good';
  if (utilization > 70) return 'fair';
  return 'poor';
};

/* ────────────────── legend items (for header bar) ────────────────── */

/** Translation keys for legend labels — the consumer resolves via useLang.t() */
export const LEGEND_ITEMS = [
  { labelKey: 'home.map.legend.clean' as const, color: '#4A7C5C' },
  { labelKey: 'home.map.legend.qualified' as const, color: '#D9A441' },
  { labelKey: 'home.map.legend.adverse' as const, color: '#C94A4A' },
  { labelKey: 'home.map.legend.disclaimer' as const, color: '#7c5cbf' },
  { labelKey: 'home.map.legend.pending' as const, color: '#c3cdd5' },
] as const;
