'use client';

/**
 * BudgetTab — deep-dive on a county's budget execution and debt position.
 *
 * Shows top-level allocation/spend KPIs, a sector donut + ranked list,
 * debt breakdown by lender, and pending-bill aging buckets. Extracted
 * into its own chunk so the recharts + debt-breakdown weight only
 * downloads when a user actually clicks the tab.
 */
import { useLang } from '@/lib/i18n/LangProvider';
import { useCountyPendingBills } from '@/lib/react-query/useDebt';
import { CountyComprehensive } from '@/types';
import { FileWarning } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import ModelledDataNote from '@/components/ModelledDataNote';
import { fmtKES, PALETTE, pct } from '../shared';
import KPI from './KPI';

export default function BudgetTab({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { budget, debt } = data;
  const { data: countyPendingBills } = useCountyPendingBills(data.id.toString());
  const [activeSector, setActiveSector] = useState<string | null>(null);

  const sectors = useMemo(
    () =>
      Object.entries(budget.sector_breakdown)
        .map(([name, vals], i) => ({
          name: name.length > 22 ? name.slice(0, 20) + '...' : name,
          fullName: name,
          allocated: vals.allocated,
          spent: vals.spent,
          fill: PALETTE[i % PALETTE.length],
        }))
        .sort((a, b) => b.allocated - a.allocated)
        .slice(0, 10),
    [budget.sector_breakdown]
  );

  const totalSectorAlloc = sectors.reduce((sum, s) => sum + s.allocated, 0);
  const totalSectorSpent = sectors.reduce((sum, s) => sum + s.spent, 0);
  const topSector = sectors[0];
  const active = activeSector
    ? sectors.find((s) => s.fullName === activeSector) || null
    : null;
  const displayed = active || topSector || null;
  const displayedPct = displayed && totalSectorAlloc > 0
    ? (displayed.allocated / totalSectorAlloc) * 100
    : 0;
  const displayedUtil = displayed && displayed.allocated > 0
    ? (displayed.spent / displayed.allocated) * 100
    : 0;
  const pieData = sectors.map((s) => ({
    name: s.name,
    fullName: s.fullName,
    value: s.allocated,
    fill: s.fill,
  }));

  return (
    <div className='space-y-5'>
      <ModelledDataNote />
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

      {/* Sector spending — editorial donut + ranked list */}
      {sectors.length > 0 && (
        <div className='relative overflow-hidden rounded-2xl border border-gray-100 dark:border-neutral-border bg-gradient-to-br from-white via-white to-gov-sage/5 dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated'>
          {/* Ambient color wash from top sector */}
          <div
            aria-hidden
            className='absolute -top-20 -right-20 w-64 h-64 rounded-full blur-3xl opacity-20'
            style={{ backgroundColor: displayed?.fill || '#3b82f6' }}
          />

          {/* Header */}
          <div className='relative flex items-start justify-between gap-4 px-5 pt-5 pb-2'>
            <div>
              <div className='flex items-center gap-2 mb-1'>
                <div className='h-5 w-1 rounded-full bg-gov-forest' />
                <h3 className='text-base font-semibold text-gray-900 dark:text-neutral-text'>
                  {t('county.budget.sector_spending')}
                </h3>
              </div>
              <p className='text-xs text-gray-500 dark:text-neutral-muted/80 ml-3'>
                {t('county.budget.sector_explore_hint').replace('{n}', String(sectors.length))}
              </p>
            </div>
            <div className='hidden sm:flex items-center gap-3 text-[11px] text-gray-500 dark:text-neutral-muted/80'>
              <div className='flex items-center gap-1.5'>
                <div className='w-2.5 h-2.5 rounded-sm bg-gray-200 dark:bg-surface-sunken' />
                <span>{t('county.budget.legend_allocated')}</span>
              </div>
              <div className='flex items-center gap-1.5'>
                <div className='w-2.5 h-2.5 rounded-sm bg-emerald-500' />
                <span>{t('county.budget.legend_spent')}</span>
              </div>
            </div>
          </div>

          <div className='relative grid grid-cols-1 lg:grid-cols-12 gap-4 px-5 pb-5 pt-2'>
            {/* LEFT: interactive donut with live center label (5/12) */}
            <div className='lg:col-span-5'>
              <div className='relative h-[320px]'>
                <ResponsiveContainer width='100%' height='100%'>
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey='value'
                      nameKey='fullName'
                      cx='50%'
                      cy='50%'
                      outerRadius='90%'
                      innerRadius='62%'
                      paddingAngle={1.5}
                      strokeWidth={0}
                      onMouseEnter={(e) => setActiveSector(e?.fullName || null)}
                      onMouseLeave={() => setActiveSector(null)}>
                      {pieData.map((e, i) => (
                        <Cell
                          key={i}
                          fill={e.fill}
                          opacity={
                            activeSector && activeSector !== e.fullName ? 0.35 : 1
                          }
                          style={{ transition: 'opacity 200ms ease-out', cursor: 'pointer' }}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>

                {/* Center label — swaps between total + hovered sector */}
                <div className='absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center'>
                  {active ? (
                    <>
                      <div
                        className='w-2 h-2 rounded-full mb-2'
                        style={{ backgroundColor: active.fill }}
                      />
                      <div className='text-[11px] uppercase tracking-widest font-semibold text-gray-400 dark:text-neutral-muted/80 px-4 leading-tight'>
                        {active.fullName}
                      </div>
                      <div className='text-lg font-bold tabular-nums text-gray-900 dark:text-neutral-text mt-1'>
                        {fmtKES(active.allocated)}
                      </div>
                      <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 tabular-nums mt-0.5'>
                        {displayedPct.toFixed(1)}% {t('county.budget.of_top_10')}
                      </div>
                      <div className='mt-2 px-2 py-0.5 rounded-full bg-emerald-50 border border-emerald-100'>
                        <span className='text-[11px] font-semibold text-emerald-700 tabular-nums'>
                          {displayedUtil.toFixed(0)}% {t('county.budget.executed_suffix')}
                        </span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className='text-[11px] uppercase tracking-widest font-semibold text-gray-400 dark:text-neutral-muted/80'>
                        {t('county.budget.top_10_sectors')}
                      </div>
                      <div className='text-2xl font-bold tabular-nums text-gray-900 dark:text-neutral-text mt-1'>
                        {fmtKES(totalSectorAlloc)}
                      </div>
                      <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                        {t('county.budget.allocated_lower')}
                      </div>
                      <div className='mt-2 flex items-baseline gap-1'>
                        <span className='text-sm font-bold text-emerald-700 tabular-nums'>
                          {fmtKES(totalSectorSpent)}
                        </span>
                        <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80'>
                          {t('county.budget.spent_lower')}
                        </span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* RIGHT: ranked sector cards with allocation + utilization (7/12) */}
            <div className='lg:col-span-7 space-y-1.5'>
              {sectors.map((s, idx) => {
                const pctOfTotal =
                  totalSectorAlloc > 0 ? (s.allocated / totalSectorAlloc) * 100 : 0;
                const utilization = s.allocated > 0 ? (s.spent / s.allocated) * 100 : 0;
                const isActive = activeSector === s.fullName;
                const utilColor =
                  utilization >= 85
                    ? 'text-emerald-700'
                    : utilization >= 60
                      ? 'text-teal-700'
                      : utilization >= 30
                        ? 'text-amber-700'
                        : 'text-rose-700';
                return (
                  <button
                    key={s.fullName}
                    type='button'
                    onMouseEnter={() => setActiveSector(s.fullName)}
                    onMouseLeave={() => setActiveSector(null)}
                    className={`w-full text-left rounded-xl px-3 py-2.5 transition-all border ${
                      isActive
                        ? 'border-gray-200 dark:border-neutral-border bg-white dark:bg-surface-base shadow-sm'
                        : 'border-transparent hover:bg-white/60 dark:bg-surface-elevated'
                    }`}>
                    <div className='flex items-center gap-3'>
                      {/* Rank */}
                      <div className='text-[11px] font-bold text-gray-400 dark:text-neutral-muted/80 tabular-nums w-4 flex-shrink-0'>
                        {(idx + 1).toString().padStart(2, '0')}
                      </div>
                      {/* Color dot */}
                      <div
                        className='w-2.5 h-2.5 rounded-full flex-shrink-0'
                        style={{ backgroundColor: s.fill }}
                      />
                      {/* Name */}
                      <div className='flex-1 min-w-0'>
                        <div className='text-sm font-semibold text-gray-800 dark:text-neutral-text truncate'>
                          {s.fullName}
                        </div>
                      </div>
                      {/* Allocation */}
                      <div className='text-right flex-shrink-0'>
                        <div className='text-sm font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                          {fmtKES(s.allocated)}
                        </div>
                        <div className='text-[11px] text-gray-400 dark:text-neutral-muted/80 tabular-nums'>
                          {pctOfTotal.toFixed(1)}%
                        </div>
                      </div>
                    </div>

                    {/* Layered progress bar: allocated track + spent fill */}
                    <div className='mt-2 ml-11'>
                      <div className='relative h-1.5 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                        <div
                          className='absolute inset-y-0 left-0 rounded-full'
                          style={{
                            width: `${Math.min(utilization, 100)}%`,
                            backgroundColor: s.fill,
                            transition: 'width 400ms ease-out',
                          }}
                        />
                      </div>
                      <div className='flex items-center justify-between mt-1'>
                        <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 tabular-nums'>
                          <span className={`font-semibold ${utilColor}`}>
                            {utilization.toFixed(0)}%
                          </span>{' '}
                          {t('county.budget.executed_suffix')}
                        </span>
                        <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 tabular-nums'>
                          {fmtKES(s.spent)} {t('county.budget.spent_lower')}
                        </span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

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
