'use client';

/**
 * DebtSourceReconciliation
 *
 * Kenya's National Treasury and CBK publish two debt totals that almost — but
 * not quite — agree. This component shows both, cites where each comes from,
 * and explains the ~5% gap so citizens aren't left wondering which number is
 * real.
 *
 * The primary (live) figure is the sum of every registered debt instrument in
 * the CBK Public Debt Statistical Bulletin — our ETL pulls the PDF daily and
 * sums line items. That total is what appears as the headline everywhere else
 * on the site.
 *
 * The reference figure is CBK's published annual debt stock (the one you see
 * quoted in newspapers and Treasury BPS documents). It's a manually-curated
 * input today because CBK only publishes this aggregate quarterly, in prose.
 *
 * The gap exists because the aggregate includes items the loan register
 * doesn't yet reflect: forex revaluation adjustments, T-bill rollovers
 * in transit, and month-end vs year-end consolidation timing.
 */

import { motion } from 'framer-motion';
import { BookOpen, Database, GitCompareArrows, Info } from 'lucide-react';

export interface ReconciliationInput {
  primary_source?: string;
  primary_value_kes?: number;
  secondary_source?: string;
  secondary_value_kes?: number;
  secondary_year?: number;
  percent_diff?: number;
  status?: string;
  note?: string;
}

interface Props {
  reconciliation?: ReconciliationInput | null;
  lastUpdated?: string | null; // ISO timestamp from overview endpoint
}

function fmtT(kes?: number): string {
  if (!kes || kes <= 0) return '—';
  if (kes >= 1_000_000_000_000) return `${(kes / 1_000_000_000_000).toFixed(2)}T`;
  if (kes >= 1_000_000_000) return `${(kes / 1_000_000_000).toFixed(0)}B`;
  return `${kes.toLocaleString()}`;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
}

export default function DebtSourceReconciliation({ reconciliation, lastUpdated }: Props) {
  // Defensive: if backend didn't attach reconciliation, don't render.
  if (!reconciliation || reconciliation.primary_value_kes == null) return null;

  const primary = reconciliation.primary_value_kes ?? 0;
  const secondary = reconciliation.secondary_value_kes ?? 0;
  const diffKES = Math.abs(secondary - primary);
  const diffPct = reconciliation.percent_diff ?? (primary > 0 ? (diffKES / primary) * 100 : 0);

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5 }}
      className='rounded-2xl border border-neutral-border/40 bg-white/70 dark:bg-surface-elevated backdrop-blur-sm overflow-hidden'>
      {/* Header */}
      <div className='border-b border-neutral-border/40 bg-gradient-to-r from-gov-sand/40 via-white to-transparent dark:from-surface-elevated/40 dark:via-surface-base/20 dark:to-transparent px-5 sm:px-7 py-4'>
        <div className='flex items-start gap-3'>
          <div className='rounded-lg bg-gov-forest/10 text-gov-forest dark:text-emerald-100 p-2 mt-0.5'>
            <GitCompareArrows size={18} />
          </div>
          <div className='flex-1 min-w-0'>
            <h3 className='font-display text-lg sm:text-xl text-gov-dark dark:text-white leading-tight'>
              Sources &amp; Reconciliation
            </h3>
            <p className='text-xs sm:text-sm text-neutral-muted mt-0.5'>
              Kenya&apos;s debt is published as two slightly-different totals. We show both, with
              the sources, so you can verify.
            </p>
          </div>
        </div>
      </div>

      {/* Two source cards */}
      <div className='grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-neutral-border/40'>
        {/* ── Primary: live loans register ── */}
        <div className='p-5 sm:p-6 relative'>
          <div className='absolute top-4 right-4 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-gov-forest dark:text-emerald-100 bg-gov-forest/10 px-2 py-0.5 rounded-full'>
            <span className='relative flex h-1.5 w-1.5'>
              <span className='animate-ping absolute inline-flex h-full w-full rounded-full bg-gov-forest opacity-60' />
              <span className='relative inline-flex rounded-full h-1.5 w-1.5 bg-gov-forest' />
            </span>
            Live
          </div>
          <div className='flex items-center gap-2 mb-2'>
            <Database size={14} className='text-gov-forest dark:text-emerald-100' />
            <span className='text-xs font-semibold uppercase tracking-wider text-gov-forest dark:text-emerald-100'>
              Outstanding Loan Register
            </span>
          </div>
          <div className='metric-large text-gov-dark dark:text-white tabular-nums'>
            KES {fmtT(primary)}
          </div>
          <p className='text-xs text-neutral-muted mt-2 leading-relaxed'>
            Sum of every registered debt instrument — multilateral loans, bilateral loans,
            commercial loans, Eurobonds, Treasury bonds, T-bills, CBK advances, and pending
            bills.
          </p>
          <dl className='mt-4 space-y-1.5 text-[11px]'>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Source</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>
                CBK Public Debt Statistical Bulletin
              </dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Fetch</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>
                Daily · PDF parsed server-side
              </dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Last updated</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>{fmtDate(lastUpdated)}</dd>
            </div>
          </dl>
          <p className='mt-3 text-[10px] uppercase tracking-wider text-gov-forest dark:text-emerald-100 font-semibold'>
            ← Used as the headline figure on this site
          </p>
        </div>

        {/* ── Reference: Treasury aggregate ── */}
        <div className='p-5 sm:p-6 relative'>
          <div className='absolute top-4 right-4 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-gov-gold bg-gov-gold/15 px-2 py-0.5 rounded-full'>
            <BookOpen size={10} />
            Reference
          </div>
          <div className='flex items-center gap-2 mb-2'>
            <BookOpen size={14} className='text-gov-gold' />
            <span className='text-xs font-semibold uppercase tracking-wider text-gov-gold'>
              Treasury Annual Aggregate
            </span>
          </div>
          <div className='metric-large text-gov-dark dark:text-white tabular-nums'>
            KES {fmtT(secondary)}
          </div>
          <p className='text-xs text-neutral-muted mt-2 leading-relaxed'>
            CBK/Treasury&apos;s consolidated stock published in annual statistical bulletins and
            the Budget Policy Statement. This is the figure quoted in news headlines.
          </p>
          <dl className='mt-4 space-y-1.5 text-[11px]'>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Source</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>
                CBK Annual Report · Treasury BPS
              </dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Fetch</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>
                Quarterly · manual reconciliation
              </dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Covers</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>
                FY {reconciliation.secondary_year ?? '—'}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Gap explainer strip */}
      <div className='border-t border-neutral-border/40 bg-gov-sand/30 px-5 sm:px-7 py-4'>
        <div className='flex items-start gap-3'>
          <div className='rounded-full bg-white dark:bg-surface-base border border-gov-gold/40 text-gov-gold p-1.5 mt-0.5 flex-shrink-0'>
            <Info size={14} />
          </div>
          <div className='flex-1'>
            <div className='flex flex-wrap items-baseline gap-x-2 gap-y-0.5'>
              <span className='text-sm font-semibold text-gov-dark dark:text-white'>
                Gap: KES {fmtT(diffKES)}
              </span>
              <span className='text-xs text-neutral-muted'>
                ({diffPct.toFixed(1)}% of the loan register)
              </span>
            </div>
            <p className='text-[12px] text-neutral-muted leading-relaxed mt-1'>
              The two totals disagree because Treasury&apos;s aggregate is published after
              consolidation adjustments — forex revaluation on external debt, T-bill rollovers
              in transit, and pending bills yet to be booked into the instrument register.
              Treasury reconciles these at year-end. We use the live loan register as the
              headline because it&apos;s tied directly to the CBK bulletin our ETL parses
              daily — so the number you see moves when CBK publishes fresh data.
            </p>
            {/* The backend may attach a `note` string describing the
                reconciliation state (divergent / consistent / which table
                won), but it's phrased for developers — it references
                internal table names like `DebtTimeline` and `loans_table`.
                Keep it out of the UI; it belongs in logs. The paragraph
                above already explains the gap in plain language, and the
                percent-diff chip signals severity. */}
          </div>
        </div>
      </div>
    </motion.section>
  );
}
