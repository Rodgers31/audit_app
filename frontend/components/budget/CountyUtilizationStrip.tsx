'use client';

/**
 * CountyUtilizationStrip
 *
 * A two-column strip showing the best-performing and worst-performing
 * counties by budget utilisation. Keeps the page tight — the full county
 * story lives on /counties.
 *
 * Styled as a "leaderboard" with rank pills on the left and a link to the
 * counties page for the full ranking of 47.
 */

import { motion } from 'framer-motion';
import { ArrowRight, TrendingDown, TrendingUp } from 'lucide-react';
import Link from 'next/link';

export interface CountyUtilRow {
  county: string;
  allocated?: number;
  spent?: number;
  utilization: number;
}

interface Props {
  top: CountyUtilRow[];
  bottom: CountyUtilRow[];
  average?: number;
}

function fmtB(v?: number): string {
  if (v == null || v <= 0) return '—';
  const b = v >= 1_000_000_000 ? v / 1_000_000_000 : v;
  if (b >= 1000) return `${(b / 1000).toFixed(1)}T`;
  return `${b.toFixed(1)}B`;
}

export default function CountyUtilizationStrip({ top, bottom, average }: Props) {
  const hasTop = (top ?? []).length > 0;
  const hasBottom = (bottom ?? []).length > 0;
  if (!hasTop && !hasBottom) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5 }}
      className='space-y-3'>
      <div className='flex items-baseline justify-between gap-3 flex-wrap'>
        <div>
          <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/80 dark:text-emerald-100/80'>
            County execution
          </div>
          <h3 className='font-display text-xl sm:text-[22px] text-gov-dark dark:text-white leading-tight mt-0.5'>
            Who&apos;s spending their share — and who isn&apos;t
          </h3>
        </div>
        {average != null && average > 0 && (
          <div className='text-[11px] text-neutral-muted'>
            National average{' '}
            <span className='text-gov-dark dark:text-white font-bold tabular-nums'>{average.toFixed(1)}%</span>
          </div>
        )}
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 gap-3'>
        {/* Top performers */}
        {hasTop && (
          <div className='rounded-2xl bg-white dark:bg-surface-base border border-gov-sage/25 shadow-surface overflow-hidden'>
            <div className='bg-gradient-to-r from-gov-sage/15 via-white to-transparent border-b border-neutral-border/30 px-5 py-3 flex items-center gap-2'>
              <TrendingUp size={16} className='text-gov-sage' />
              <h4 className='text-[13px] font-semibold text-gov-dark dark:text-white'>Best absorbed</h4>
              <span className='text-[10.5px] text-neutral-muted ml-auto'>
                Money reaches citizens
              </span>
            </div>
            <div className='p-4 space-y-2.5'>
              {top.map((c, i) => (
                <div key={c.county} className='flex items-center gap-3'>
                  <span className='w-7 h-7 rounded-full bg-gov-sage/15 text-gov-sage text-[12px] font-bold flex items-center justify-center tabular-nums'>
                    {i + 1}
                  </span>
                  <div className='flex-1 min-w-0'>
                    <div className='flex items-baseline justify-between gap-2 mb-1'>
                      <span className='text-[12.5px] font-semibold text-gov-dark dark:text-white truncate'>
                        {c.county}
                      </span>
                      <span className='text-[12.5px] font-bold text-gov-sage tabular-nums'>
                        {c.utilization.toFixed(1)}%
                      </span>
                    </div>
                    <div className='h-1.5 rounded-full bg-neutral-border/30 overflow-hidden'>
                      <motion.div
                        initial={{ width: 0 }}
                        whileInView={{ width: `${Math.min(c.utilization, 100)}%` }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8, delay: i * 0.05 }}
                        className='h-full rounded-full'
                        style={{ background: 'linear-gradient(90deg, #4B8564, #1F4A30)' }}
                      />
                    </div>
                    {c.allocated != null && c.spent != null && (
                      <div className='flex items-center justify-between mt-1 text-[10px] text-neutral-muted tabular-nums'>
                        <span>Spent KES {fmtB(c.spent)}</span>
                        <span>of {fmtB(c.allocated)}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bottom performers */}
        {hasBottom && (
          <div className='rounded-2xl bg-white dark:bg-surface-base border border-gov-copper/25 shadow-surface overflow-hidden'>
            <div className='bg-gradient-to-r from-gov-copper/12 via-white to-transparent dark:from-surface-elevated/40 dark:via-surface-base/20 dark:to-transparent border-b border-neutral-border/30 px-5 py-3 flex items-center gap-2'>
              <TrendingDown size={16} className='text-gov-copper' />
              <h4 className='text-[13px] font-semibold text-gov-dark dark:text-white'>Biggest underspend</h4>
              <span className='text-[10.5px] text-neutral-muted ml-auto'>
                Unreleased to citizens
              </span>
            </div>
            <div className='p-4 space-y-2.5'>
              {bottom.map((c, i) => (
                <div key={c.county} className='flex items-center gap-3'>
                  <span className='w-7 h-7 rounded-full bg-gov-copper/15 text-gov-copper text-[12px] font-bold flex items-center justify-center tabular-nums'>
                    {i + 1}
                  </span>
                  <div className='flex-1 min-w-0'>
                    <div className='flex items-baseline justify-between gap-2 mb-1'>
                      <span className='text-[12.5px] font-semibold text-gov-dark dark:text-white truncate'>
                        {c.county}
                      </span>
                      <span className='text-[12.5px] font-bold text-gov-copper tabular-nums'>
                        {c.utilization.toFixed(1)}%
                      </span>
                    </div>
                    <div className='h-1.5 rounded-full bg-neutral-border/30 overflow-hidden'>
                      <motion.div
                        initial={{ width: 0 }}
                        whileInView={{ width: `${Math.min(c.utilization, 100)}%` }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8, delay: i * 0.05 }}
                        className='h-full rounded-full'
                        style={{ background: 'linear-gradient(90deg, #B83E3E, #7E2424)' }}
                      />
                    </div>
                    {c.allocated != null && c.spent != null && (
                      <div className='flex items-center justify-between mt-1 text-[10px] text-neutral-muted tabular-nums'>
                        <span>Spent KES {fmtB(c.spent)}</span>
                        <span>of {fmtB(c.allocated)}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className='flex justify-end'>
        <Link
          href='/counties'
          className='inline-flex items-center gap-1 text-[12px] font-semibold text-gov-forest dark:text-emerald-100 hover:text-gov-dark dark:text-white transition-colors'>
          See all 47 counties
          <ArrowRight size={13} />
        </Link>
      </div>
    </motion.section>
  );
}
