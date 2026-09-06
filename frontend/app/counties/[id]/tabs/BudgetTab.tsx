'use client';

/**
 * BudgetTab — deep-dive on a county's budget execution and debt position.
 *
 * Shows top-level allocation/spend KPIs, debt breakdown by lender, and
 * pending-bill aging buckets. The sector donut that used to sit between them
 * was withdrawn — see the note further down.
 */
import { useLang } from '@/lib/i18n/LangProvider';
import { useCountyPendingBills } from '@/lib/react-query/useDebt';
import { CountyComprehensive } from '@/types';
import { FileWarning } from 'lucide-react';
import ModelledDataNote from '@/components/ModelledDataNote';
import { fmtKES, pct } from '../shared';
import KPI from './KPI';

export default function BudgetTab({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { budget, debt } = data;
  const { data: countyPendingBills } = useCountyPendingBills(data.id.toString());

  return (
    <div className='space-y-5'>
      <ModelledDataNote budgetSource={budget.source} />
      {/* Top-level budget stats */}
      <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
        <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-4'>{t('county.budget.summary')}</h3>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-6'>
          <KPI
            label={t('county.budget.total_allocated')}
            value={fmtKES(budget.total_allocated)}
            accent='text-blue-700'
          />
          <KPI
            label={t('county.budget.total_spent')}
            value={fmtKES(budget.total_spent)}
            sub={`${pct(budget.utilization_rate)} ${t('county.budget.execution_suffix')}`}
            accent='text-emerald-700'
          />
          <KPI
            label={t('county.budget.development')}
            value={
              budget.development_budget
                ? fmtKES(budget.development_budget)
                : t('county.budget.unavailable')
            }
            sub={budget.development_budget ? undefined : t('county.budget.not_classified')}
            accent='text-amber-700'
          />
          <KPI
            label={t('county.budget.recurrent')}
            value={
              budget.recurrent_budget
                ? fmtKES(budget.recurrent_budget)
                : t('county.budget.unavailable')
            }
            sub={budget.recurrent_budget ? undefined : t('county.budget.not_classified')}
            accent='text-purple-700'
          />
        </div>
      </div>

      {/* The county "Sector Spending" donut and ranked list were withdrawn
          (credibility audit F11). `sector_breakdown` is not extracted from any
          county publication: across all 47 counties there is exactly ONE
          distinct set of sector shares — Health 25%, Education 20%, Roads 15%,
          Water 10%, Agriculture 8%, Administration 7%, Trade 5%, Environment
          4%, Social 3%, Other 3% — a fixed template applied to each county's
          headline budget. Two counties opened side by side falsify it. The
          per-sector "spent" figures are also mutually inconsistent with the
          county's own total_spent (Baringo's sum is 154% of it). Restore only
          when county sector lines are extracted from CoB CBIRR tables. */}

      {/* Debt breakdown */}
      {debt.breakdown.length > 0 && (
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
          <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-4'>
            {t('county.budget.debt_breakdown')}
          </h3>
          <div className='space-y-3'>
            {debt.breakdown.map((d, i) => {
              const pctOfTotal = debt.total_debt > 0 ? (d.outstanding / debt.total_debt) * 100 : 0;
              return (
                <div key={i}>
                  <div className='flex items-center justify-between mb-1'>
                    <span className='text-sm text-gray-700 dark:text-neutral-muted'>{d.lender}</span>
                    <span className='text-sm font-semibold text-gray-900 dark:text-neutral-text tabular-nums'>
                      {fmtKES(d.outstanding)}
                    </span>
                  </div>
                  <div className='h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                    <div
                      className='h-full rounded-full bg-red-400'
                      style={{ width: `${Math.min(pctOfTotal, 100)}%` }}
                    />
                  </div>
                  <div className='text-[11px] text-gray-400 dark:text-neutral-muted/80 mt-0.5'>
                    {pct(pctOfTotal)} {t('county.budget.of_total_debt')}
                  </div>
                </div>
              );
            })}
          </div>
          <div className='mt-4 pt-3 border-t border-gray-100 dark:border-neutral-border flex items-center justify-between text-sm'>
            <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.budget.total_debt_label')}</span>
            <span className='font-bold text-red-700'>{fmtKES(debt.total_debt)}</span>
          </div>
        </div>
      )}

      {/* County Pending Bills Breakdown */}
      {(countyPendingBills || debt.pending_bills > 0) && (
        <div className='bg-white dark:bg-surface-base rounded-xl border border-red-200 p-5'>
          <div className='flex items-center gap-2 mb-4'>
            <FileWarning size={16} className='text-red-600' />
            <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text'>
              {t('county.budget.pending_bills_title')}
            </h3>
            <span className='text-sm font-bold text-red-700 ml-auto'>
              {fmtKES(countyPendingBills?.total_pending || debt.pending_bills)}
            </span>
          </div>

          {/* Breakdown by type */}
          {countyPendingBills?.breakdown_by_type &&
            countyPendingBills.breakdown_by_type.length > 0 && (
              <div className='space-y-2 mb-4'>
                <h4 className='text-xs font-semibold text-gray-500 dark:text-neutral-muted/80 uppercase tracking-wider'>
                  {t('county.budget.pending_by_type')}
                </h4>
                {countyPendingBills.breakdown_by_type.map((row) => {
                  const colors: Record<string, string> = {
                    supplier_arrears: 'bg-red-500',
                    salary: 'bg-blue-500',
                    pension: 'bg-purple-500',
                    statutory: 'bg-amber-500',
                    court_awards: 'bg-orange-500',
                  };
                  const bgColor =
                    Object.entries(colors).find(([k]) => row.type.toLowerCase().includes(k))?.[1] ||
                    'bg-gray-400';
                  return (
                    <div key={row.type}>
                      <div className='flex items-center justify-between mb-0.5'>
                        <span className='text-xs text-gray-700 dark:text-neutral-muted'>
                          {row.type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                        </span>
                        <span className='text-xs font-semibold text-gray-800 dark:text-neutral-text'>
                          {fmtKES(row.amount)}
                        </span>
                      </div>
                      <div className='h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                        <div
                          className={`h-full rounded-full ${bgColor}`}
                          style={{ width: `${Math.min(row.percentage, 100)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

          {/* Aging buckets */}
          {countyPendingBills?.aging_buckets && countyPendingBills.aging_buckets.length > 0 && (
            <div>
              <h4 className='text-xs font-semibold text-gray-500 dark:text-neutral-muted/80 uppercase tracking-wider mb-2'>
                {t('county.budget.pending_aging')}
              </h4>
              <div className='flex h-4 rounded-full overflow-hidden'>
                {countyPendingBills.aging_buckets.map((bucket) => {
                  const colors: Record<string, string> = {
                    '0-30d': '#22c55e',
                    '31-90d': '#f59e0b',
                    '91-180d': '#f97316',
                    '180d+': '#ef4444',
                  };
                  return (
                    <div
                      key={bucket.bucket}
                      className='transition-all'
                      style={{
                        width: `${bucket.percentage}%`,
                        backgroundColor: colors[bucket.bucket] || '#94a3b8',
                      }}
                      title={`${bucket.bucket}: ${fmtKES(bucket.amount)} (${bucket.percentage.toFixed(1)}%)`}
                    />
                  );
                })}
              </div>
              <div className='flex items-center gap-3 mt-2 text-[11px] text-gray-400 dark:text-neutral-muted/80 flex-wrap'>
                {countyPendingBills.aging_buckets.map((bucket) => {
                  const colors: Record<string, string> = {
                    '0-30d': '#22c55e',
                    '31-90d': '#f59e0b',
                    '91-180d': '#f97316',
                    '180d+': '#ef4444',
                  };
                  return (
                    <div key={bucket.bucket} className='flex items-center gap-1'>
                      <div
                        className='w-2 h-2 rounded-full'
                        style={{ backgroundColor: colors[bucket.bucket] || '#94a3b8' }}
                      />
                      <span>
                        {bucket.bucket}: {fmtKES(bucket.amount)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!countyPendingBills && debt.pending_bills > 0 && (
            <p className='text-xs text-gray-500 dark:text-neutral-muted/80'>
              {t('county.budget.pending_fallback').replace('{amount}', fmtKES(debt.pending_bills))}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
