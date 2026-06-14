'use client';

/**
 * FiscalTrendStrip
 *
 * Compact multi-year view: three paired sparklines for Budget, Revenue,
 * and Borrowing across the fiscal years we have in `fiscal_history`.
 * Designed to sit below the hero — answers "is the fiscal gap widening
 * or narrowing?" at a glance.
 *
 * Each card shows:
 *   — a sparkline + year labels
 *   — the latest value (tabular-nums, KES)
 *   — the CAGR-style delta across the series
 *
 * Clicking a year pill below the sparklines could drive a year selector
 * upstream, but for now we keep it read-only — the hero anchors on the
 * latest fiscal year.
 */

import { motion } from 'framer-motion';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { useMemo } from 'react';

export interface FiscalHistoryRow {
  fiscal_year: string;
  appropriated_budget?: number | null;
  total_revenue?: number | null;
  total_borrowing?: number | null;
  debt_service_cost?: number | null;
  county_allocation?: number | null;
}

interface Props {
  history: FiscalHistoryRow[];
}

function fmtB(v?: number | null): string {
  if (v == null || v <= 0) return '—';
  if (v >= 1000) return `${(v / 1000).toFixed(2)}T`;
  return `${v.toFixed(0)}B`;
}

function pctChange(a?: number | null, b?: number | null): number | null {
  if (a == null || b == null || b === 0) return null;
  return ((a - b) / b) * 100;
}

interface SeriesCard {
  label: string;
  key: keyof FiscalHistoryRow;
  accent: string;
  gradStart: string;
  gradEnd: string;
  tagline: string;
}

const CARDS: SeriesCard[] = [
  {
    label: 'Appropriated budget',
    key: 'appropriated_budget',
    accent: '#1B3A2A',
    gradStart: '#3B7251',
    gradEnd: '#1F4A30',
    tagline: "Parliament's approved spend ceiling.",
  },
  {
    label: 'Tax + non-tax revenue',
    key: 'total_revenue',
    accent: '#3E6B84',
    gradStart: '#5088A8',
    gradEnd: '#2F5A70',
    tagline: 'What KRA + SOEs brought in.',
  },
  {
    label: 'New borrowing',
    key: 'total_borrowing',
    accent: '#9E3030',
    gradStart: '#B83E3E',
    gradEnd: '#7E2424',
    tagline: 'Gap filled with fresh debt.',
  },
  {
    label: 'Debt service',
    key: 'debt_service_cost',
    accent: '#A6781F',
    gradStart: '#B38628',
    gradEnd: '#7D591A',
    tagline: 'Old loans being repaid.',
  },
];

export default function FiscalTrendStrip({ history }: Props) {
  const sorted = useMemo(
    () =>
      [...(history ?? [])]
        .filter((r) => r && r.fiscal_year)
        .sort((a, b) => (a.fiscal_year > b.fiscal_year ? 1 : -1)),
    [history]
  );

  if (sorted.length < 2) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5 }}
      className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
      <div className='flex items-baseline justify-between mb-4'>
        <div>
          <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/80 dark:text-emerald-100/80'>
            The past four budgets
          </div>
          <h3 className='font-display text-xl sm:text-[22px] text-gov-dark dark:text-white leading-tight mt-0.5'>
            Is the gap narrowing, or is debt growing faster than revenue?
          </h3>
        </div>
      </div>

      <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5'>
        {CARDS.map((c) => {
          const values = sorted.map((r) => ({
            year: r.fiscal_year.replace('FY ', ''),
            value: (r[c.key] as number | null) ?? 0,
          }));
          const latest = values[values.length - 1];
          const first = values[0];
          const max = Math.max(...values.map((v) => v.value), 1);
          const delta = pctChange(latest.value, first.value);
          const isUp = delta != null && delta > 0.5;
          const isDown = delta != null && delta < -0.5;
          return (
            <div
              key={c.label}
              className='relative rounded-xl bg-white dark:bg-surface-base border border-neutral-border/30 shadow-sm overflow-hidden'>
              <div
                className='absolute inset-x-0 top-0 h-0.5'
                style={{ background: `linear-gradient(90deg, ${c.gradStart}, ${c.gradEnd})` }}
              />
              <div className='p-4'>
                <div className='flex items-baseline justify-between gap-2 mb-1'>
                  <span className='text-[11px] font-semibold text-gov-dark dark:text-white'>{c.label}</span>
                  {delta != null && (
                    <span
                      className={`inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full tabular-nums ${
                        isUp
                          ? c.key === 'total_borrowing' || c.key === 'debt_service_cost'
                            ? 'bg-red-50 text-red-600'
                            : 'bg-green-50 text-green-700'
                          : isDown
                            ? c.key === 'total_borrowing' || c.key === 'debt_service_cost'
                              ? 'bg-green-50 text-green-700'
                              : 'bg-red-50 text-red-600'
                            : 'bg-gray-100 dark:bg-surface-elevated text-gray-500 dark:text-neutral-muted/80'
                      }`}>
                      {isUp ? <ArrowUp size={10} /> : isDown ? <ArrowDown size={10} /> : <Minus size={10} />}
                      {Math.abs(delta).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div className='font-display text-lg sm:text-xl text-gov-dark dark:text-white tabular-nums leading-none'>
                  KES {fmtB(latest.value)}
                </div>
                <p className='text-[10.5px] text-neutral-muted mt-1 leading-snug'>{c.tagline}</p>
                {/* Sparkbars */}
                <div className='mt-3 flex items-end gap-1 h-10'>
                  {values.map((v, i) => {
                    const h = (v.value / max) * 100;
                    const isLatest = i === values.length - 1;
                    return (
                      <div key={v.year} className='flex-1 flex flex-col items-center gap-0.5'>
                        <div
                          className='w-full rounded-t-sm transition-all'
                          style={{
                            height: `${Math.max(h, 8)}%`,
                            background: isLatest
                              ? `linear-gradient(180deg, ${c.gradStart}, ${c.gradEnd})`
                              : '#E2DDD5',
                          }}
                        />
                        <span className='text-[9px] text-neutral-muted tabular-nums'>{v.year}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </motion.section>
  );
}
