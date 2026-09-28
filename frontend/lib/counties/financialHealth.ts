import type { TranslationKey } from '@/lib/i18n/messages';

/**
 * AuditGava's financial-health index bands, matching backend/main.py's
 * _HEALTH_GRADE_BANDS. This is a chosen site grade for the composite health
 * score, not the OAG opinion or the separate accountability score.
 */
export const FINANCIAL_HEALTH_BANDS = [
  { grade: 'A', min: 85, labelKey: 'county.acct.grade_excellent', fill: '#42765d', badgeClass: 'bg-emerald-500 text-white' },
  { grade: 'B+', min: 70, labelKey: 'county.acct.grade_good', fill: '#9db993', badgeClass: 'bg-green-500 text-white' },
  { grade: 'B', min: 55, labelKey: 'county.acct.grade_fair', fill: '#bd9155', badgeClass: 'bg-amber-500 text-white' },
  { grade: 'B-', min: 40, labelKey: 'county.acct.grade_needs_improvement', fill: '#b36b5c', badgeClass: 'bg-orange-500 text-white' },
  { grade: 'C', min: 0, labelKey: 'county.acct.grade_poor', fill: '#884c45', badgeClass: 'bg-red-500 text-white' },
] as const satisfies ReadonlyArray<{
  grade: string;
  min: number;
  labelKey: TranslationKey;
  fill: string;
  badgeClass: string;
}>;

export function financialHealthBand(score: number | null | undefined) {
  if (typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 100) {
    return null;
  }
  return FINANCIAL_HEALTH_BANDS.find((band) => score >= band.min) ?? null;
}
