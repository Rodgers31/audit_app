'use client';

import { usePendingBillsSummary } from '@/lib/react-query';
import { toRawKES } from '@/lib/utils';
import { useDebtTimeline, useNationalDebtOverview } from '@/lib/react-query/useDebt';
import { AnimatePresence, motion } from 'framer-motion';
import { Info, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

/**
 * Info button + modal explaining why the hero total-debt figure
 * differs from the loans-card outstanding figure.
 *
 * Both figures are read from the API here rather than described from memory.
 * The previous copy had them the wrong way round: it said the hero was a
 * Treasury "aggregate projection" INCLUDING pending bills, when the hero is
 * `/api/v1/debt/national` -> `total_outstanding`, the sum of our own
 * instrument register, which EXCLUDES pending bills (`_is_debt_loan`). It also
 * explained the gap as pending bills and FX rounding — a confident account of
 * a discrepancy the site's own audit banner calls unreconciled.
 *
 * Rendered through a portal: this modal mounts inside HeroSection, whose
 * ancestors are framer-motion elements. A transformed ancestor creates a
 * stacking context, so `position: fixed; z-50` was scoped inside it and later
 * sections painted over the panel.
 */

interface Props {
  /** Which context the button appears in — adjusts the accent sentence. */
  context: 'hero' | 'loans';
  className?: string;
}

export default function DebtExplainerModal({ context, className = '' }: Props) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const { data: pendingData } = usePendingBillsSummary();
  const { data: overview } = useNationalDebtOverview();
  const { data: timelineResp } = useDebtTimeline();

  // The API returns raw KES. Appending " B" to it printed
  // "≈ 1128944197956 B" on screen — a number in no unit at all.
  const pendingBillsLabel = pendingData?.total_pending_amount
    ? `≈ KES ${(pendingData.total_pending_amount / 1e12).toFixed(2)}T`
    : '—';

  // Read both figures from the API rather than describing them from memory,
  // so this explanation cannot drift away from what the page is showing.
  const fmtT = (kes?: number | null) =>
    kes != null ? `KES ${(kes / 1e12).toFixed(2)}T` : '—';

  // The query returns the raw envelope; the payload is under `data`. Same
  // unwrapping HeroSection does — without it every figure here rendered as an
  // em dash while the hero beside it showed the number.
  const apiData = (overview as any)?.data ?? overview;
  const registerTotal = apiData?.total_outstanding ?? apiData?.total_debt ?? null;
  const registerRows: number | null = apiData?.loan_count ?? null;

  const timeline = (timelineResp as any)?.timeline ?? timelineResp ?? [];
  const newest = Array.isArray(timeline) && timeline.length
    ? [...timeline].sort((a: any, b: any) => (a.year ?? 0) - (b.year ?? 0)).slice(-1)[0]
    : null;
  const publishedTotal = newest ? toRawKES(newest.total, newest.unit) : null;
  const publishedYear = newest?.year ?? null;

  const gapKes =
    registerTotal != null && publishedTotal != null
      ? Math.abs(registerTotal - publishedTotal)
      : null;
  const gapPct =
    gapKes != null && registerTotal ? (gapKes / registerTotal) * 100 : null;

  return (
    <>
      {/* Trigger — small "i" icon */}
      <button
        type='button'
        onClick={() => setOpen(true)}
        aria-label='Why do the debt figures differ?'
        className={`tap-24 inline-flex items-center justify-center rounded-full transition-colors
          ${
            context === 'hero'
              ? 'w-5 h-5 bg-gov-dark/10 hover:bg-gov-dark/20 text-gov-dark/50 hover:text-gov-dark/80 dark:text-white/50 dark:hover:text-white/80'
              : 'w-4 h-4 bg-gov-copper/10 hover:bg-gov-copper/20 text-gov-copper/60 hover:text-gov-copper'
          } ${className}`}>
        <Info className={context === 'hero' ? 'w-3 h-3' : 'w-2.5 h-2.5'} />
      </button>

      {/* Modal — portalled to <body>.
          Mounted inside HeroSection, whose ancestors include framer-motion
          elements; a transformed ancestor creates a stacking context, which
          scoped `position: fixed; z-50` inside it and let later sections paint
          over the panel. A portal escapes that entirely. */}
      {mounted &&
        createPortal(
          <AnimatePresence>
            {open && (
              <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className='fixed inset-0 z-[99] bg-black/40 backdrop-blur-sm'
              onClick={() => setOpen(false)}
            />

            {/* Panel */}
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
              className='fixed inset-0 z-[100] m-auto flex h-fit max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-neutral-border/30 dark:bg-surface-base'>
              {/* Header */}
              <div className='flex shrink-0 items-center justify-between border-b border-neutral-border/20 px-6 pb-3 pt-5'>
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
              <div className='min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5 text-sm leading-relaxed text-gov-dark/80 dark:text-white/80'>
                <p>
                  You may notice two different debt totals on this page. They come from
                  <strong> two official but distinct datasets</strong>, each measuring Kenya's
                  public debt in a slightly different way:
                </p>

                {/* Card 1 — the hero figure: OUR register */}
                <div className='rounded-xl border border-gov-dark/10 bg-gov-sand/30 px-4 py-3'>
                  <p className='text-xs font-semibold uppercase tracking-wider text-gov-dark/50 dark:text-white/50 mb-1'>
                    🇰🇪 Hero banner — &quot;Total Debt&quot; · {fmtT(registerTotal)}
                  </p>
                  <p className='font-semibold text-gov-dark dark:text-white mb-1'>
                    Our own sum of individual instruments
                    {registerRows != null ? ` (${registerRows} rows)` : ''}
                  </p>
                  <p>
                    Every debt instrument we hold — each lender, principal and outstanding
                    balance — added up. The rows trace to the CBK Public Debt Statistical
                    Bulletin of <strong>April 2025</strong>, so this is a figure for that date,
                    not for the end of the year. It <strong>excludes</strong> pending bills:
                    those are unpaid invoices, not borrowing, and they have their own panel.
                  </p>
                </div>

                {/* Card 2 — what CBK itself publishes */}
                <div className='rounded-xl border border-gov-copper/15 bg-gov-copper/[0.04] px-4 py-3'>
                  <p className='text-xs font-semibold uppercase tracking-wider text-gov-copper/60 mb-1'>
                    🏛️ CBK&apos;s own published total · {fmtT(publishedTotal)}
                  </p>
                  <p className='font-semibold text-gov-dark dark:text-white mb-1'>
                    CBK Statistical Bulletin, Table 4.1.3
                    {publishedYear ? ` — December ${publishedYear}` : ''}
                  </p>
                  <p>
                    A single aggregate the Central Bank publishes for the whole stock of public
                    debt. We do not build it; we read it. It also excludes pending bills.
                  </p>
                </div>

                {/* The gap — stated, not explained away */}
                <div className='rounded-xl border border-gov-gold/40 bg-gov-gold/[0.07] px-4 py-3'>
                  <p className='text-xs font-semibold uppercase tracking-wider text-gov-gold mb-1'>
                    ⚠️ The gap is unreconciled
                  </p>
                  <p>
                    The two differ by{' '}
                    <strong>
                      {gapKes != null ? fmtT(gapKes) : '—'}
                      {gapPct != null ? ` (${gapPct.toFixed(1)}%)` : ''}
                    </strong>
                    , and <strong>we cannot yet say which is right</strong>. Pending bills do not
                    explain it — both figures exclude them ({pendingBillsLabel}).
                  </p>
                  <p className='mt-2'>
                    Two things make the gap harder to explain, not easier. Our register is dated
                    April 2025 yet exceeds CBK&apos;s figure for the following December, and debt
                    does not fall over a year of continued borrowing. Until that is resolved we
                    report the difference rather than account for it.
                  </p>
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
              <div className='flex shrink-0 justify-end border-t border-neutral-border/20 bg-neutral-border/5 px-6 py-3'>
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
          </AnimatePresence>,
          document.body
        )}
    </>
  );
}
