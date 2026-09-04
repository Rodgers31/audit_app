'use client';

/**
 * MaturityLadder — when Kenya's Treasury bonds fall due.
 *
 * Restored after withdrawal. The version removed before launch drew its
 * "walls" from 3 of 28 register rows, collapsed five separate Eurobond issues
 * onto one 2034 date, and filed World Bank IDA, AfDB, JICA, AFD and KfW
 * credits under "Revolving & pooled instruments — continuously rolled over",
 * which amortising term loans are not (credibility audit F24).
 *
 * This one reads GET /api/v1/debt/instruments: individual securities extracted
 * from CBK's own "Issues of Treasury Bonds" table, each with its ISIN,
 * maturity date and coupon.
 *
 * The one thing this component must never do is imply the bars add up to
 * Kenya's debt. They cover ~60% of the published Treasury-bond stock and
 * nothing of the external book, so the coverage line is rendered as part of
 * the chart, not tucked into a tooltip.
 */

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { CalendarClock, Info } from 'lucide-react';
import api from '@/lib/api/axios';

interface LadderBucket {
  year: number;
  face_value: number;
  instruments: number;
}

interface InstrumentsResponse {
  status: 'success' | 'unavailable';
  reason?: string;
  message?: string;
  is_debt_total?: boolean;
  not_a_stock_measure?: string;
  coverage?: { coverage_ratio?: number | null };
  withheld_count?: number;
  instrument_count?: number;
  ladder: LadderBucket[];
  source?: { publisher?: string; title?: string; url?: string; as_of?: string };
}

function fmtKES(v: number): string {
  if (v >= 1e12) return `KES ${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `KES ${(v / 1e9).toFixed(0)}B`;
  return `KES ${(v / 1e6).toFixed(0)}M`;
}

export default function MaturityLadder() {
  const { data, isLoading, isError, refetch } = useQuery<InstrumentsResponse>({
    queryKey: ['debt', 'instruments'],
    queryFn: async () => (await api.get<InstrumentsResponse>('/debt/instruments')).data,
    staleTime: 60 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className='rounded-2xl border border-neutral-border/40 bg-white/60 dark:bg-surface-elevated h-64 animate-pulse' />
    );
  }

  // A failed request also leaves `data` undefined, so folding it in here
  // reported a backend outage as "no bond register has been ingested" — a
  // different claim, and the one this component exists to keep distinct.
  if (isError) {
    return (
      <section className='rounded-2xl border border-neutral-border/60 bg-surface-sunken/40 px-5 py-5'>
        <div className='flex items-start gap-2.5'>
          <Info className='w-4 h-4 mt-0.5 flex-shrink-0 text-amber-600' />
          <div className='text-[12.5px] leading-relaxed text-neutral-muted'>
            <span className='font-semibold text-gov-dark dark:text-white'>
              The maturity profile could not be loaded.
            </span>{' '}
            This is a problem reaching the server, not a statement about the
            bond register.
            <button
              type='button'
              onClick={() => refetch()}
              className='ml-2 underline underline-offset-2 hover:text-gov-forest dark:hover:text-emerald-100'>
              Try again
            </button>
          </div>
        </div>
      </section>
    );
  }

  // Absent is not "no debt falls due". Say which it is.
  if (!data || data.status !== 'success' || data.ladder.length === 0) {
    return (
      <section className='rounded-2xl border border-neutral-border/60 bg-surface-sunken/40 px-5 py-5'>
        <div className='flex items-start gap-2.5'>
          <Info className='w-4 h-4 mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70' />
          <p className='text-[12.5px] leading-relaxed text-neutral-muted'>
            <span className='font-semibold text-gov-dark dark:text-white'>
              No bond register has been ingested yet.
            </span>{' '}
            {data?.message ??
              'This is not a finding that no government debt falls due.'}
          </p>
        </div>
      </section>
    );
  }

  const max = Math.max(...data.ladder.map((b) => b.face_value));
  const total = data.ladder.reduce((s, b) => s + b.face_value, 0);
  const coverage = data.coverage?.coverage_ratio ?? null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5 }}
      className='rounded-2xl border border-neutral-border/40 bg-white/70 dark:bg-surface-elevated overflow-hidden'>
      <div className='px-5 sm:px-7 pt-5 pb-3 border-b border-neutral-border/40'>
        <h2 className='font-display text-xl sm:text-2xl text-gov-dark dark:text-white flex items-center gap-2'>
          <CalendarClock className='text-gov-forest dark:text-emerald-100' size={22} />
          When Treasury bonds fall due
        </h2>
        <p className='text-sm text-neutral-muted mt-1'>
          {data.instrument_count} securities from the Central Bank&apos;s bond
          register, each with its own maturity date and coupon.
        </p>
      </div>

      <div className='px-5 sm:px-7 py-5 space-y-1.5'>
        {data.ladder.map((b) => (
          <div key={b.year} className='flex items-center gap-3'>
            <span className='w-11 shrink-0 font-mono text-[11px] tabular-nums text-neutral-muted'>
              {b.year}
            </span>
            <div className='flex-1 h-5 rounded-sm bg-neutral-border/25 overflow-hidden'>
              <motion.div
                initial={{ width: 0 }}
                whileInView={{ width: `${(b.face_value / max) * 100}%` }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                className='h-full rounded-sm bg-gradient-to-r from-gov-forest to-gov-sage'
              />
            </div>
            <span className='w-20 shrink-0 text-right font-mono text-[11px] tabular-nums text-gov-dark dark:text-white'>
              {fmtKES(b.face_value)}
            </span>
            <span className='w-14 shrink-0 text-right text-[11px] text-neutral-muted'>
              {b.instruments} {b.instruments === 1 ? 'bond' : 'bonds'}
            </span>
          </div>
        ))}
      </div>

      {/* The scope caveat is part of the chart, not a footnote. Bars that look
          like "Kenya's debt by year" are exactly how the withdrawn version
          misled. */}
      <div className='border-t border-neutral-border/40 bg-surface-sunken/40 px-5 sm:px-7 py-3.5'>
        <p className='text-[11.5px] leading-relaxed text-neutral-muted'>
          <span className='font-semibold text-gov-dark dark:text-white'>
            These bars are not Kenya&apos;s total debt.
          </span>{' '}
          They show {fmtKES(total)} of domestic Treasury bonds sold at auction
          since 2007
          {coverage != null && ` — about ${Math.round(coverage * 100)}% of the bond stock the Central Bank publishes`}
          . Bonds issued outside auctions, paper predating 2007 and the entire
          external book are not here, and neither are Treasury bills.
          {/* eslint-disable-next-line local/no-zero-fallback-on-published-figure -- a register with nothing withheld genuinely has zero withheld, and the sentence is simply not rendered */}
          {(data.withheld_count ?? 0) > 0 && (
            <>
              {' '}
              {data.withheld_count} further{' '}
              {data.withheld_count === 1 ? 'security is' : 'securities are'} held
              back because the source lists more than one maturity for them and
              we cannot tell which year the money falls due in.
            </>
          )}
          {data.source?.url && (
            <>
              {' '}
              <a
                href={data.source.url}
                target='_blank'
                rel='noopener noreferrer'
                className='underline hover:no-underline'>
                Source: {data.source.publisher}
              </a>
              .
            </>
          )}
        </p>
      </div>
    </motion.section>
  );
}
