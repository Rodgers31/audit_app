import { evidenceUrl } from '@/lib/evidence/qualification';
import type { AuditAmountCoverage, MoneyFlowData } from '@/types';

/** Presentation only: amounts and efficiency are supplied by the existing money-flow API. */
export type FlowTone = 'neutral' | 'allocation' | 'good' | 'fair' | 'low';

/** The API publishes efficiency to two decimals. Keep that precision at band edges. */
export function formatEfficiency(score: number): string {
  return score.toLocaleString('en-KE', { maximumFractionDigits: 2 });
}

export function efficiencyTone(score: number | null): FlowTone {
  return score == null ? 'neutral' : score >= 70 ? 'good' : score >= 50 ? 'fair' : 'low';
}

export function formatFlowKES(amount: number | null | undefined): string {
  if (amount == null) return '—';
  const abs = Math.abs(amount);
  if (abs >= 1e12) return `KES ${(amount / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(amount / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `KES ${(amount / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `KES ${(amount / 1e3).toFixed(0)}K`;
  return `KES ${amount.toLocaleString()}`;
}

export const COUNTY_SPENDING_TARGET = 70;

export type CountySpendingPoint = { id: string; label: string; percentage: number | null };

export function sameMoneyFlowPeriod(data: MoneyFlowData | null | undefined, year: string) {
  const barePeriod = (value: string) => value.replace(/^FY\s*/i, '').trim();
  return data && barePeriod(data.fiscal_year) === barePeriod(year) ? data : null;
}

function reportedSpendingShare(data: MoneyFlowData) {
  if (data.budget_source === 'cra_model' || data.budget_source === 'mixed') return null;
  const allocated = data.stages?.find((stage) => stage.stage === 'Allocated');
  const spent = data.stages?.find((stage) => stage.stage === 'Spent');
  const efficiency = data.efficiency_score;
  if (
    allocated?.data_unavailable || allocated?.amount == null ||
    !Number.isFinite(allocated.amount) || allocated.amount <= 0 ||
    spent?.data_unavailable || spent?.amount == null ||
    !Number.isFinite(spent.amount) || spent.amount < 0 ||
    efficiency == null || !Number.isFinite(efficiency) || efficiency < 0
  ) return null;
  return efficiency;
}

export function nationalDistributionGuide(data: MoneyFlowData | null | undefined, year: string) {
  const current = sameMoneyFlowPeriod(data, year);
  if (current?.budget_source !== 'cob_cbirr' || !evidenceUrl(current.source_document_url)) return null;
  return reportedSpendingShare(current);
}

export function countyDistributionPoints(flows: MoneyFlowData[], year: string) {
  const counties = new Map<string, CountySpendingPoint>();
  for (const flow of flows) {
    if (flow.county_id == null || !flow.county_name || !sameMoneyFlowPeriod(flow, year)) continue;
    const id = String(flow.county_id);
    counties.set(id, {
      id,
      label: flow.county_name.replace(/ County$/, ''),
      percentage: reportedSpendingShare(flow),
    });
  }
  return Array.from(counties.values());
}

export interface MoneyFlowInsights {
  audit_amount_coverage?: AuditAmountCoverage;
  allocated: number | null;
  spent: number | null;
  flagged: number | null;
  gap: number | null;
  unspentPct: number | null;
  efficiency: number | null;
}

export interface CountyFlowRow {
  audit_amount_coverage?: AuditAmountCoverage;
  county_id: string;
  county_name: string;
  efficiency_score: number | null;
  flagged_amount: number | null;
  total_gap: number;
  allocated: number | null;
  spent: number | null;
}

export type CountySortKey = 'efficiency' | 'flagged' | 'gap' | 'name' | 'allocated';

/** Missing expenditure alone is not evidence of a modelled allocation. */
export function isProjectedMoneyFlow(data: MoneyFlowData | null | undefined): boolean {
  return Boolean(
    data?.budget_source === 'cra_model' &&
      data.stages?.some((stage) => stage.stage === 'Allocated' && stage.amount != null) &&
      !data.stages?.some(
        (stage) => ['Spent', 'Flagged', 'Released'].includes(stage.stage) && stage.amount != null
      ) &&
      data.efficiency_score == null
  );
}

/** Coverage follows the API; absence never means zero or an unpublished report. */
export function auditAmountCoverageNote(coverage?: AuditAmountCoverage, lang = 'en'): string | null {
  if (!coverage) return null;
  if (lang === 'sw') {
    if (coverage.reason === 'fiscal_period_not_found') return 'Kipindi cha fedha hakipatikani.';
    if (coverage.reason === 'no_findings') return 'Hakuna matokeo ya ukaguzi yaliyorekodiwa kwa kipindi hiki.';
    if (coverage.reason === 'no_publishable_findings') return 'Hakuna matokeo ya ukaguzi yenye marejeo yanayopatikana kwa kipindi hiki.';
    const counts = `Matokeo ${coverage.findings_with_amount} kati ya ${coverage.total_findings} yana kiasi halali; kiasi ${coverage.findings_without_amount} hakipo na ${coverage.findings_with_invalid_amount} si halali.`;
    return coverage.status === 'partial'
      ? `Jumla ya sehemu: ${counts}`
      : coverage.status === 'unavailable'
        ? `Kiasi hakipatikani: ${counts}`
        : `Kiasi kilichorekodiwa kinajumuisha matokeo yote ${coverage.total_findings} yenye marejeo.`;
  }
  if (coverage.reason === 'fiscal_period_not_found') return 'Fiscal period unavailable.';
  if (coverage.reason === 'no_findings') return 'No audit findings recorded for this period.';
  if (coverage.reason === 'no_publishable_findings') return 'No cited audit findings available for this period.';
  const counts = `${coverage.findings_with_amount} of ${coverage.total_findings} cited findings have finite recorded amounts; ${coverage.findings_without_amount} missing and ${coverage.findings_with_invalid_amount} invalid amounts.`;
  return coverage.status === 'partial'
    ? `Partial subtotal: ${counts}`
    : coverage.status === 'unavailable'
      ? `Amount unavailable: ${counts}`
      : `Recorded amounts cover all ${coverage.total_findings} cited findings.`;
}
