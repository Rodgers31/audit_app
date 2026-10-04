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

import FigureEvidence from '@/components/evidence/FigureEvidence';
import { motion } from 'framer-motion';
import { AlertTriangle, ChevronDown } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { Qualifications } from '@/lib/evidence/qualification';

export interface ExecutionRow {
  qualifications?: Qualifications;
  sector: string;
  allocated: number; // KES — revised gross estimates (see ExecutionMeasure)
  spent: number; // KES — actual expenditure
  unspent: number;
  execution_rate: number; // %
  /** Page of the COB report the row's Sector Summary is on, e.g. "p.94". */
  page_ref?: string | null;
}

/** The document the rows come from (`execution_source`). */
export interface ExecutionSource {
  publisher?: string | null;
  title?: string | null;
  url?: string | null;
}

/** How much of the ministerial budget the rows cover (`execution_coverage`). */
export interface ExecutionCoverage {
  sectors_expected?: number;
  sectors_reported?: number;
  sectors_missing?: string[];
  sector_expenditure_bn?: string | null;
  mda_expenditure_bn?: string | null;
  /** null = not checked; false = the sectors do not sum to the report's MDA total. */
  reconciles?: boolean | null;
}

/** What the rows leave out (`execution_excludes`). */
export interface ExecutionExcludes {
  label: string;
  description: string;
  expenditure_bn: string;
}

interface Props {
  rows: ExecutionRow[];
  /** FY the CoB execution figures actually cover (may lag the page's selected FY). */
  fiscalYear?: string;
  source?: ExecutionSource | null;
  coverage?: ExecutionCoverage | null;
  excludes?: ExecutionExcludes | null;
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
  // COB's ten national sectors, as the annual NG-BIRR names them (#241).
  'Agriculture, Rural and Urban Development': { start: '#6AA38B', end: '#3A7058', base: '#4E8770' },
  'Energy, Infrastructure and ICT': { start: '#C99641', end: '#8C6621', base: '#AC7E31' },
  'Environment Protection, Water, and Natural Resources': { start: '#5B9774', end: '#2F6B4A', base: '#417F5E' },
  'General Economic and Commercial Affairs': { start: '#B66F4B', end: '#7B4628', base: '#96593B' },
  'Governance, Justice, Law and Order': { start: '#7B8591', end: '#3F4754', base: '#5B6672' },
  'National Security': { start: '#576573', end: '#303944', base: '#414D59' },
  'Public Administration and International Relations': { start: '#5088A8', end: '#2F5A70', base: '#3E6B84' },
  'Social Protection, Culture and Recreation': { start: '#C37A94', end: '#8A4B62', base: '#A46278' },
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

/** KSh-billion strings from the API ("1982.52") → "1.98T" / "62.4B". */
function fmtBn(bn?: string | null): string | null {
  if (bn == null) return null;
  const v = Number(bn);
  if (!Number.isFinite(v)) return null;
  return fmtB(v * 1_000_000_000);
}

export default function ExecutionAuditLens({ rows, fiscalYear, source, coverage, excludes }: Props) {
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
              Actual expenditure against revised gross estimates for the whole of {fiscalYear} —
              the latest full-year report from the Controller of Budget — and may lag the fiscal
              year selected above.
            </p>
          )}
          {/* What the rows cover and what they leave out. Stated, because a
              total over ministries alone reads as the whole budget otherwise. */}
          {(coverage || excludes) && (
            <p className='text-[11px] text-neutral-muted mt-1 max-w-2xl' data-testid='execution-coverage'>
              {coverage?.sectors_reported != null && coverage?.sectors_expected != null && (
                <>
                  Ministerial spending, {coverage.sectors_reported} of {coverage.sectors_expected}{' '}
                  sectors
                  {coverage.sectors_missing && coverage.sectors_missing.length > 0 && (
                    <> (not shown: {coverage.sectors_missing.join(', ')} — figures did not reconcile)</>
                  )}
                  {/* In billions, as COB prints them: at trillion precision a
                      2.77B gap rounds to "2.21T vs 2.22T" and reads as noise. */}
                  {coverage.reconciles === false && coverage.mda_expenditure_bn && coverage.sector_expenditure_bn && (
                    <>
                      ; the sectors sum to KES {coverage.sector_expenditure_bn}B against the
                      report&apos;s ministerial total of KES {coverage.mda_expenditure_bn}B
                    </>
                  )}
                  .{' '}
                </>
              )}
              {excludes && fmtBn(excludes.expenditure_bn) && (
                <>
                  Excludes {excludes.label} (KES {fmtBn(excludes.expenditure_bn)} spent:{' '}
                  {excludes.description}).
                </>
              )}
            </p>
          )}
        </div>
        <div className='rounded-lg border border-gov-copper/30 bg-gov-copper/5 px-4 py-2 text-right'>
          <div className='text-[11px] uppercase tracking-wider font-semibold text-gov-copper'>
            Total unspent
          </div>
          <div className='font-display text-xl text-gov-dark dark:text-white leading-tight tabular-nums'>
            KES {fmtB(totals.unspent)}
          </div>
          <div className='text-[11px] text-neutral-muted leading-tight tabular-nums'>
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
                    <span
                      title={r.sector}
                      className='text-[12px] sm:text-[13px] font-semibold text-gov-dark dark:text-white truncate'>
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
                    <span className='absolute inset-0 flex items-center justify-center text-[11px] font-bold text-white/95 mix-blend-luminosity tabular-nums'>
                      {execPct.toFixed(0)}% spent
                    </span>
                  </div>
                </div>
                {/* Values */}
                <div className='flex-shrink-0 text-right w-28 sm:w-36'>
                  <div className='text-[12px] font-semibold text-gov-dark dark:text-white tabular-nums'>
                    KES {fmtB(r.spent)}
                  </div>
                  <div className='text-[11px] text-neutral-muted tabular-nums'>
                    of {fmtB(r.allocated)}
                  </div>
                </div>
                {/* Gap chip */}
                <div className='flex-shrink-0 w-20 text-right'>
                  <span
                    className={`inline-flex items-center gap-0.5 text-[11px] font-semibold px-2 py-0.5 rounded-full tabular-nums ${
                      severity === 'ok'
                        ? 'bg-green-50 text-green-700'
                        : severity === 'warn'
                          ? 'bg-amber-50 text-amber-700'
                          : 'bg-red-50 text-red-600'
                    }`}>
                    {severity !== 'ok' && <AlertTriangle size={10} />}
                    {fmtB(r.unspent)}
                  </span>
                  <div className='text-[11px] text-neutral-muted tabular-nums mt-0.5'>
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
              <div className='px-4'><FigureEvidence label={`${r.sector} allocation and expenditure`} labelKey='evidence.label.sector_allocation' labelValues={{ sector: r.sector }} qualifications={r.qualifications} /></div>
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

      <div className='mt-4 pt-3 border-t border-neutral-border/30 flex items-center justify-between text-[11px] text-neutral-muted'>
        <span data-testid='execution-source'>
          Source:{' '}
          {source?.url ? (
            <a href={source.url} target='_blank' rel='noopener noreferrer' className='underline'>
              {source.publisher ?? 'Controller of Budget'} · {source.title ?? 'Budget Implementation Review'}
            </a>
          ) : (
            <>Controller of Budget · Budget Implementation Review</>
          )}
          {' '}· sector summaries, Section 4
        </span>
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
