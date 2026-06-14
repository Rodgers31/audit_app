'use client';

/**
 * ExecutionAuditLens
 *
 * The audit-focused view of budget execution: for each sector, how much of
 * the approved allocation did the government actually manage to spend, and
 * how much sits UNSPENT at year-end?
 *
 * Sorted by unspent amount DESCENDING so the sector with the biggest
 * absorption gap appears first. Budget-bar-graph with a strong underscore
 * on the gap — unspent money is a governance failure that doesn't show up
 * in headline numbers.
 *
 * Click a row to reveal a plain-English commentary interpreting whether
 * low execution is a capacity issue (procurement delays) or a deliberate
 * in-year funding squeeze (cash rationing by Treasury).
 */

import { motion } from 'framer-motion';
import { AlertTriangle, ChevronDown } from 'lucide-react';
import { useMemo, useState } from 'react';

export interface ExecutionRow {
  sector: string;
  allocated: number; // KES (absolute, in KES not billions from backend)
  spent: number;
  unspent: number;
  execution_rate: number; // %
}

interface Props {
  rows: ExecutionRow[];
  /** FY the CoB execution figures actually cover (may lag the page's selected FY). */
  fiscalYear?: string;
}

const SECTOR_TONE: Record<string, { start: string; end: string; base: string }> = {
  Health: { start: '#D96868', end: '#8C2E2E', base: '#B94040' },
  Education: { start: '#4B8564', end: '#1F4A30', base: '#2F6343' },
  Infrastructure: { start: '#B38628', end: '#7D591A', base: '#A6781F' },
  'Water & Sanitation': { start: '#5088A8', end: '#2F5A70', base: '#3E6B84' },
  Agriculture: { start: '#6AA38B', end: '#3A7058', base: '#4E8770' },
  Administration: { start: '#7B8591', end: '#3F4754', base: '#5B6672' },
  'Trade & Enterprise': { start: '#B66F4B', end: '#7B4628', base: '#96593B' },
  Environment: { start: '#5B9774', end: '#2F6B4A', base: '#417F5E' },
  'Social Protection': { start: '#C37A94', end: '#8A4B62', base: '#A46278' },
  'Defense & Security': { start: '#576573', end: '#303944', base: '#414D59' },
  Energy: { start: '#C99641', end: '#8C6621', base: '#AC7E31' },
  Other: { start: '#9AA3AE', end: '#6B7280', base: '#838C99' },
};

const FALLBACK = { start: '#6B7280', end: '#3F4754', base: '#4B5563' };

function toneFor(name: string) {
  return SECTOR_TONE[name] ?? FALLBACK;
}

function fmtB(kes: number): string {
  const b = kes >= 1_000_000_000 ? kes / 1_000_000_000 : kes;
  if (b >= 1000) return `${(b / 1000).toFixed(2)}T`;
  if (b >= 1) return `${b.toFixed(1)}B`;
  return `${b.toFixed(2)}B`;
}

/* plain-English commentary per execution-rate band */
function commentary(rate: number, sector: string): string {
  if (rate >= 85) {
    return `Strong absorption — ${sector} ministries deployed almost all of their ceiling. Often a sign of mature procurement pipelines or fixed recurrent commitments (salaries, utilities).`;
  }
  if (rate >= 70) {
    return `Typical absorption — within normal Kenyan public-sector range. The unspent residual usually reflects development projects that started late in the fiscal year.`;
  }
  if (rate >= 50) {
    return `Weak absorption. The residual is large enough to be structural — common causes are delayed Treasury exchequer releases, stalled procurement, or AIE delays.`;
  }
  return `Critical under-execution. This is money Parliament approved that did not reach citizens. Typically indicates chronic procurement failure, litigation-blocked projects, or severe in-year funding cuts by the National Treasury.`;
}

export default function ExecutionAuditLens({ rows, fiscalYear }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const sorted = useMemo(() => {
    return (rows ?? [])
      .filter((r) => r.allocated > 0)
      .map((r) => ({ ...r }))
      .sort((a, b) => b.unspent - a.unspent);
  }, [rows]);

  const totals = useMemo(() => {
    const alloc = sorted.reduce((s, r) => s + r.allocated, 0);
    const spent = sorted.reduce((s, r) => s + r.spent, 0);
    const unspent = sorted.reduce((s, r) => s + r.unspent, 0);
    const rate = alloc > 0 ? (spent / alloc) * 100 : 0;
    return { alloc, spent, unspent, rate };
  }, [sorted]);

  if (sorted.length === 0) return null;

  // Scale bars to the largest allocation across all sectors (not sorted[0],
  // which is the largest UNSPENT row — those differ whenever a well-funded
  // sector also absorbs well). Using sorted[0] produced >100% widths.
  const maxAlloc = Math.max(...sorted.map((r) => r.allocated), 1);

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.55 }}
      className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-7'>
      <div className='flex items-start justify-between gap-4 flex-wrap mb-5'>
        <div>
          <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-copper/90'>
            The audit lens · execution{fiscalYear ? ` · ${fiscalYear}` : ''}
          </div>
          <h3 className='font-display text-xl sm:text-[22px] text-gov-dark dark:text-white leading-tight mt-0.5'>
            Where approved money went unspent
          </h3>
          <p className='text-[12.5px] text-neutral-muted mt-1 max-w-2xl'>
            Sectors sorted by the biggest <span className='font-semibold text-gov-dark dark:text-white'>absorption gap</span>{' '}
            first. Unspent money is not savings — it&apos;s approvals by Parliament that failed to reach citizens.
          </p>
          {fiscalYear && (
            <p className='text-[11px] text-gov-copper/90 mt-1.5 font-medium'>
              Execution figures cover {fiscalYear} — the latest published by the Controller of
              Budget — and may lag the fiscal year selected above.
            </p>
          )}
        </div>
        <div className='rounded-lg border border-gov-copper/30 bg-gov-copper/5 px-4 py-2 text-right'>
          <div className='text-[10px] uppercase tracking-wider font-semibold text-gov-copper'>
            Total unspent
          </div>
          <div className='font-display text-xl text-gov-dark dark:text-white leading-tight tabular-nums'>
            KES {fmtB(totals.unspent)}
          </div>
          <div className='text-[10.5px] text-neutral-muted leading-tight tabular-nums'>
            across {sorted.length} sectors · {totals.rate.toFixed(1)}% overall execution
          </div>
        </div>
      </div>

      {/* Rows */}
      <div className='space-y-2'>
        {sorted.map((r, i) => {
          const tone = toneFor(r.sector);
          const execPct = r.allocated > 0 ? (r.spent / r.allocated) * 100 : 0;
          const allocBarW = Math.max((r.allocated / maxAlloc) * 100, 20);
          const isOpen = expanded === r.sector;
          const severity =
            execPct >= 80 ? 'ok' : execPct >= 60 ? 'warn' : 'bad';
          return (
            <motion.div
              key={r.sector}
              initial={{ opacity: 0, x: -10 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: Math.min(i * 0.04, 0.3), duration: 0.3 }}
              className='rounded-xl border border-neutral-border/30 bg-white dark:bg-surface-base overflow-hidden'>
              <button
                type='button'
                onClick={() => setExpanded(isOpen ? null : r.sector)}
                className='w-full text-left px-4 py-3 flex items-center gap-3'>
                {/* Label */}
                <div className='flex-shrink-0 w-32 sm:w-40'>
                  <div className='flex items-center gap-1.5'>
                    <span
                      className='w-1.5 h-5 rounded-sm'
                      style={{
                        background: `linear-gradient(180deg, ${tone.start}, ${tone.end})`,
                      }}
                    />
                    <span className='text-[12px] sm:text-[13px] font-semibold text-gov-dark dark:text-white truncate'>
                      {r.sector}
                    </span>
                  </div>
                </div>
                {/* Bar */}
                <div className='flex-1 min-w-0'>
                  <div
                    className='relative h-6 rounded-md bg-neutral-border/25 overflow-hidden'
                    style={{ width: `${allocBarW}%` }}>
                    <div
                      className='absolute inset-y-0 left-0 rounded-md transition-all'
                      style={{
                        width: `${execPct}%`,
                        background: `linear-gradient(90deg, ${tone.start}, ${tone.end})`,
                      }}
                    />
                    <span className='absolute inset-0 flex items-center justify-center text-[10.5px] font-bold text-white/95 mix-blend-luminosity tabular-nums'>
                      {execPct.toFixed(0)}% spent
                    </span>
                  </div>
                </div>
                {/* Values */}
                <div className='flex-shrink-0 text-right w-28 sm:w-36'>
                  <div className='text-[12px] font-semibold text-gov-dark dark:text-white tabular-nums'>
                    KES {fmtB(r.spent)}
                  </div>
                  <div className='text-[10.5px] text-neutral-muted tabular-nums'>
                    of {fmtB(r.allocated)}
                  </div>
                </div>
                {/* Gap chip */}
                <div className='flex-shrink-0 w-20 text-right'>
                  <span
                    className={`inline-flex items-center gap-0.5 text-[10px] font-semibold px-2 py-0.5 rounded-full tabular-nums ${
                      severity === 'ok'
                        ? 'bg-green-50 text-green-700'
                        : severity === 'warn'
                          ? 'bg-amber-50 text-amber-700'
                          : 'bg-red-50 text-red-600'
                    }`}>
                    {severity !== 'ok' && <AlertTriangle size={10} />}
                    {fmtB(r.unspent)}
                  </span>
                  <div className='text-[9.5px] text-neutral-muted tabular-nums mt-0.5'>
                    unspent
                  </div>
                </div>
                <ChevronDown
                  size={14}
                  className={`flex-shrink-0 text-neutral-muted transition-transform ${
                    isOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>
              {isOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className='px-4 pb-3 pt-0 border-t border-neutral-border/30'>
                  <p className='text-[11.5px] text-neutral-muted leading-relaxed mt-3'>
                    {commentary(execPct, r.sector)}
                  </p>
                </motion.div>
              )}
            </motion.div>
          );
        })}
      </div>

      <div className='mt-4 pt-3 border-t border-neutral-border/30 flex items-center justify-between text-[10.5px] text-neutral-muted'>
        <span>Source: Controller of Budget · Quarterly Budget Implementation Review</span>
        <div className='flex items-center gap-3'>
          <span className='inline-flex items-center gap-1'>
            <span className='w-2 h-2 rounded-sm bg-green-500' /> ≥80%
          </span>
          <span className='inline-flex items-center gap-1'>
            <span className='w-2 h-2 rounded-sm bg-amber-500' /> 60–80%
          </span>
          <span className='inline-flex items-center gap-1'>
            <span className='w-2 h-2 rounded-sm bg-red-500' /> &lt;60%
          </span>
        </div>
      </div>
    </motion.section>
  );
}
