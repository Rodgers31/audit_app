'use client';

import { usePendingBillsSummary } from '@/lib/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { Info, X } from 'lucide-react';
import { useState } from 'react';

/**
 * Info button + modal explaining why the hero total-debt figure
 * differs from the loans-card outstanding figure.
 *
 * Hero:  uses /api/v1/debt/timeline  → National Treasury projection (includes pending bills, county-guaranteed, etc.)
 * Loans: uses /api/v1/debt/loans     → CBK per-lender actuals (granular, auditable breakdown)
 */

interface Props {
  /** Which context the button appears in — adjusts the accent sentence. */
  context: 'hero' | 'loans';
  className?: string;
}

export default function DebtExplainerModal({ context, className = '' }: Props) {
  const [open, setOpen] = useState(false);
  const { data: pendingData } = usePendingBillsSummary();

  const pendingBillsLabel = pendingData?.total_pending_amount
    ? `≈ ${Math.round(pendingData.total_pending_amount)} B`
    : '—';

  return (
    <>
      {/* Trigger — small "i" icon */}
      <button
        type='button'
        onClick={() => setOpen(true)}
        aria-label='Why do the debt figures differ?'
        className={`inline-flex items-center justify-center rounded-full transition-colors
          ${
            context === 'hero'
              ? 'w-5 h-5 bg-gov-dark/10 hover:bg-gov-dark/20 text-gov-dark/50 dark:text-white/50 hover:text-gov-dark/80 dark:text-white/80'
              : 'w-4 h-4 bg-gov-copper/10 hover:bg-gov-copper/20 text-gov-copper/60 hover:text-gov-copper'
          } ${className}`}>
        <Info className={context === 'hero' ? 'w-3 h-3' : 'w-2.5 h-2.5'} />
      </button>

      {/* Modal */}
      <AnimatePresence>
        {open && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className='fixed inset-0 bg-black/40 backdrop-blur-sm z-50'
              onClick={() => setOpen(false)}
            />

            {/* Panel */}
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
              className='fixed inset-x-4 top-[15vh] z-50 mx-auto max-w-lg bg-white dark:bg-surface-base rounded-2xl shadow-2xl ring-1 ring-neutral-border/30 overflow-hidden'>
              {/* Header */}
              <div className='flex items-center justify-between px-6 pt-5 pb-3 border-b border-neutral-border/20'>
                <div className='flex items-center gap-2'>
                  <span className='flex items-center justify-center w-7 h-7 rounded-full bg-gov-gold/15'>
                    <Info className='w-4 h-4 text-gov-gold' />
                  </span>
                  <h2 className='font-display text-base font-semibold text-gov-dark dark:text-white'>
                    Why do the debt figures differ?
                  </h2>
                </div>
                <button
                  type='button'
                  onClick={() => setOpen(false)}
                  className='rounded-full p-1.5 hover:bg-neutral-border/20 transition-colors'>
                  <X className='w-4 h-4 text-neutral-muted' />
                </button>
              </div>

              {/* Body */}
              <div className='px-6 py-5 space-y-4 text-sm text-gov-dark/80 dark:text-white/80 leading-relaxed max-h-[60vh] overflow-y-auto'>
                <p>
                  You may notice two different debt totals on this page. They come from
                  <strong> two official but distinct datasets</strong>, each measuring Kenya's
                  public debt in a slightly different way:
                </p>

                {/* Card 1 — Timeline / Hero */}
                <div className='rounded-xl border border-gov-dark/10 bg-gov-sand/30 px-4 py-3'>
                  <p className='text-xs font-semibold uppercase tracking-wider text-gov-dark/50 dark:text-white/50 mb-1'>
                    🇰🇪 Hero banner — "Total Debt"
                  </p>
                  <p className='font-semibold text-gov-dark dark:text-white mb-1'>
                    Source: National Treasury Budget Policy Statement &amp; CBK Annual Bulletin
                  </p>
                  <p>
                    This figure is the government's <strong>aggregate projection</strong> for the
                    fiscal year. It includes all public debt instruments plus items that aren't
                    broken out as individual loans — such as <em>pending bills</em>,{' '}
                    <em>county-guaranteed debt</em>, and rounding adjustments from currency
                    conversion of external debt.
                  </p>
                </div>

                {/* Card 2 — Loans card */}
                <div className='rounded-xl border border-gov-copper/15 bg-gov-copper/[0.04] px-4 py-3'>
                  <p className='text-xs font-semibold uppercase tracking-wider text-gov-copper/60 mb-1'>
                    🏛️ Loans card — "Outstanding Debt"
                  </p>
                  <p className='font-semibold text-gov-dark dark:text-white mb-1'>
                    Source: CBK Public Debt Statistical Bulletin (April 2025)
                  </p>
                  <p>
                    This figure is the <strong>sum of individual, auditable loan balances</strong>{' '}
                    reported by the Central Bank of Kenya — each lender, principal, outstanding
                    amount, and interest rate. It doesn't include off-balance-sheet items like
                    pending bills or county-guaranteed obligations.
                  </p>
                </div>

                {/* Gap explanation */}
                <div className='rounded-xl border border-neutral-border/40 bg-white dark:bg-surface-base px-4 py-3'>
                  <p className='text-xs font-semibold uppercase tracking-wider text-neutral-muted mb-1'>
                    📊 The ~1 T gap is explained by
                  </p>
                  <ul className='list-disc list-inside space-y-0.5 text-sm'>
                    <li>
                      <strong>Pending bills</strong> ({pendingBillsLabel}) — unpaid government
                      invoices
                    </li>
                    <li>
                      <strong>County-guaranteed debt</strong>
                    </li>
                    <li>
                      <strong>Projection vs. actuals</strong> — the headline figure projects to
                      end-of-FY; the loans card is a point-in-time CBK snapshot
                    </li>
                    <li>
                      <strong>FX rounding</strong> — external debt converted at different exchange
                      rate snapshots
                    </li>
                  </ul>
                </div>

                <p className='text-xs text-neutral-muted'>
                  Both numbers are sourced from official Kenyan government publications. For the
                  full detail, visit the{' '}
                  <a
                    href='https://www.centralbank.go.ke/public-debt/'
                    target='_blank'
                    rel='noopener noreferrer'
                    className='underline hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                    CBK Public Debt page
                  </a>{' '}
                  or the{' '}
                  <a
                    href='https://www.treasury.go.ke/'
                    target='_blank'
                    rel='noopener noreferrer'
                    className='underline hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                    National Treasury
                  </a>
                  .
                </p>
              </div>

              {/* Footer */}
              <div className='px-6 py-3 border-t border-neutral-border/20 bg-neutral-border/5 flex justify-end'>
                <button
                  type='button'
                  onClick={() => setOpen(false)}
                  className='rounded-lg bg-gov-dark text-white px-4 py-2 text-xs font-medium hover:bg-gov-dark/90 transition-colors'>
                  Got it
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
