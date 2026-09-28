import type { MoneyFlowData } from '@/types';

/** Presentation only: amounts and efficiency are supplied by the existing money-flow API. */
export type FlowTone = 'neutral' | 'allocation' | 'good' | 'fair' | 'low';

/** The API publishes efficiency to two decimals. Keep that precision at band edges. */
export function formatEfficiency(score: number): string {
  return score.toLocaleString('en-KE', { maximumFractionDigits: 2 });
}

export function efficiencyTone(score: number | null): FlowTone {
  return score == null ? 'neutral' : score >= 70 ? 'good' : score >= 50 ? 'fair' : 'low';
}

export function efficiencyLabel(score: number | null): string {
  return score == null
    ? 'Execution data pending'
    : score >= 70
      ? 'Good execution'
      : score >= 50
        ? 'Fair execution'
        : 'Low execution';
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

export interface MoneyFlowInsights {
  allocated: number | null;
  spent: number | null;
  flagged: number | null;
  gap: number | null;
  unspentPct: number | null;
  efficiency: number | null;
}

export interface CountyFlowRow {
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
