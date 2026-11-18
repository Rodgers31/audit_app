import type { MoneyFlowData } from '@/types';

export function countyMoneyAmounts(data: MoneyFlowData) {
  const readStage = (name: string) => {
    const row = data.stages.find(stage => stage.stage === name);
    return row && !row.data_unavailable && typeof row.amount === 'number' && Number.isFinite(row.amount)
      ? row.amount : null;
  };
  const allocated = readStage('Allocated');
  const spent = readStage('Spent');
  const difference = allocated != null && allocated >= 0 && spent != null && spent >= 0 ? allocated - spent : null;
  const unspent = difference != null && difference >= 0 ? difference : null;
  const overspent = difference != null && difference < 0 ? -difference : null;
  const ratio = allocated != null && allocated > 0 && spent != null && spent >= 0
    ? spent / allocated * 100 : null;
  const committed = typeof data.committed_amount === 'number' && Number.isFinite(data.committed_amount)
    ? data.committed_amount : null;
  const flagged = readStage('Flagged');
  const chartable = allocated != null && allocated >= 0 && spent != null && spent >= 0 &&
    Math.max(allocated, spent) > 0;
  const scale = chartable ? Math.max(allocated!, spent!) : null;
  return { allocated, spent, unspent, overspent, ratio, committed, flagged, chartable, scale };
}

export function countySpendShare(value: number) {
  if (value > 0 && value < 0.1) return '<0.1';
  const rounded = Math.round(value);
  if ((rounded === 0 && value > 0) || (rounded === 100 && value !== 100)) {
    const precise = value.toFixed(2).replace(/\.?0+$/, '');
    return precise === '100' ? `${value < 100 ? '<' : '>'}100` : precise;
  }
  return String(rounded);
}
