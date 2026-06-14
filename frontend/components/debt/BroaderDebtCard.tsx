'use client';

/**
 * BroaderDebtCard
 *
 * Displays IMF's "General Government Gross Debt" figure beside our
 * existing CBK central-government total. The two disagree by
 * ~400-600B KES — the gap is county-government debt, SOE guarantees
 * Treasury has issued, pending bills, and accumulated arrears that
 * Treasury's headline number leaves out.
 *
 * Data comes from ``/api/v1/debt/broader``, populated nightly by the
 * ``imf_weo`` seeder from IMF's DataMapper REST API. When the seeder
 * has not yet run OR the IMF API has been unreachable for long
 * enough, the component renders a muted stale/unavailable state
 * rather than a misleading zero.
 */

import { motion } from 'framer-motion';
import { ArrowUpRight, Info, Landmark, TrendingUp } from 'lucide-react';
import { useBroaderDebt } from '@/lib/react-query/useDebt';

interface Props {
  /** CBK's central-government total (KES), from the primary debt
   * endpoint. Rendered next to the IMF figure so readers can see
   * both side-by-side without cross-referencing screens. */
  cbkTotalKes: number | null | undefined;
  /** ISO date of the latest CBK bulletin, shown on the CBK card. */
  cbkAsOf?: string | null;
}

function fmtT(kes: number | null | undefined): string {
  if (!kes || kes <= 0) return '—';
  if (kes >= 1e12) return `${(kes / 1e12).toFixed(2)}T`;
  if (kes >= 1e9) return `${(kes / 1e9).toFixed(0)}B`;
  return kes.toLocaleString();
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-KE', {
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export default function BroaderDebtCard({ cbkTotalKes, cbkAsOf }: Props) {
  const { data, isLoading } = useBroaderDebt();

  // Seeder hasn't produced data yet — hide the section entirely rather
  // than show placeholder zeros that would be worse than nothing.
  if (!isLoading && (data?.status !== 'success' || !data?.latest)) {
    return null;
  }

  const latest = data?.latest;
  const imfKes = latest?.value_kes ?? null;
  const imfPct = latest?.debt_to_gdp ?? null;
  const imfYear = latest?.year;
  const isProjection = latest?.is_projection ?? false;
  const gap = cbkTotalKes && imfKes ? imfKes - cbkTotalKes : null;

  return (
    <motion.section
      id='broader'
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.5 }}
      className='space-y-4 scroll-mt-24'>
      <div>
        <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
          <TrendingUp className='text-gov-forest dark:text-emerald-100' size={24} />
          Two measures of public debt
        </h2>
        <p className='text-sm text-neutral-muted mt-1'>
          What Treasury reports vs. what IMF counts — and what the gap means.
        </p>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
        {/* CBK card (Treasury's number) */}
        <div className='rounded-2xl border border-neutral-border/50 bg-white dark:bg-surface-base p-5 shadow-surface'>
          <div className='flex items-center gap-2 text-[10px] uppercase tracking-widest text-gov-forest/70 dark:text-emerald-100/70 font-semibold'>
            <Landmark size={12} />
            Treasury / CBK
          </div>
          <div className='mt-2 flex items-baseline gap-2'>
            <span className='font-display text-3xl sm:text-4xl text-gov-dark dark:text-white tabular-nums'>
              KES {fmtT(cbkTotalKes)}
            </span>
          </div>
          <p className='text-xs text-neutral-muted mt-1.5'>
            Central Government debt — loans the National Treasury owes directly.
          </p>
          <div className='mt-3 pt-3 border-t border-neutral-border/40 text-[11px] text-neutral-muted space-y-0.5'>
            <div>
              Source:{' '}
              <a
                href='https://www.centralbank.go.ke/releases/statistical-bulletin/'
                target='_blank'
                rel='noopener noreferrer'
                className='text-gov-forest dark:text-emerald-100 hover:underline inline-flex items-center gap-0.5'>
                CBK Statistical Bulletin
                <ArrowUpRight size={11} />
              </a>
            </div>
            <div>As of {fmtDate(cbkAsOf)}</div>
          </div>
        </div>

        {/* IMF card (broader measure) */}
        <div className='rounded-2xl border border-gov-gold/40 dark:border-gov-gold/30 bg-gradient-to-br from-gov-gold/5 via-white to-gov-sand dark:from-gov-gold/[0.08] dark:via-surface-base dark:to-surface-elevated p-5 shadow-surface relative overflow-hidden'>
          <div className='absolute top-0 right-0 bg-gov-gold/15 text-gov-dark/80 dark:text-white/80 text-[9.5px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-bl-lg'>
            Broader measure
          </div>
          <div className='flex items-center gap-2 text-[10px] uppercase tracking-widest text-gov-forest/70 dark:text-emerald-100/70 font-semibold'>
            <TrendingUp size={12} />
            IMF general government
          </div>
          {isLoading ? (
            <div className='mt-2 h-10 w-40 bg-gray-200 dark:bg-surface-sunken animate-pulse rounded' />
          ) : (
            <div className='mt-2 flex items-baseline gap-2'>
              <span className='font-display text-3xl sm:text-4xl text-gov-dark dark:text-white tabular-nums'>
                KES {fmtT(imfKes)}
              </span>
              {imfPct != null && (
                <span className='text-sm font-semibold text-gov-forest dark:text-emerald-100'>
                  {imfPct.toFixed(1)}% GDP
                </span>
              )}
            </div>
          )}
          <p className='text-xs text-neutral-muted mt-1.5'>
            Includes counties, SOE debt, pension arrears, and pending bills —
            the measure credit-rating agencies and IMF Article IV use.
          </p>
          <div className='mt-3 pt-3 border-t border-gov-gold/30 text-[11px] text-neutral-muted space-y-0.5'>
            <div>
              Source:{' '}
              <a
                href={data?.source?.dataset_url ?? 'https://www.imf.org/external/datamapper'}
                target='_blank'
                rel='noopener noreferrer'
                className='text-gov-forest dark:text-emerald-100 hover:underline inline-flex items-center gap-0.5'>
                IMF World Economic Outlook
                <ArrowUpRight size={11} />
              </a>
            </div>
            <div>
              {imfYear ? `${imfYear}${isProjection ? ' (projection)' : ''}` : '—'}
              {data?.stale && (
                <span className='ml-2 text-amber-600 font-medium'>
                  · data stale ({data.vintage_age_days}d old)
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Accountability explainer. Copy adjusts when the gap is small
          (< 1T) so we don't oversell a 200–500B delta as a scandal — for
          Kenya the counties/SOE/arrears overhang turns out to be modest
          compared to what it is in, say, Brazil or South Africa. */}
      <div className='rounded-xl bg-gov-forest/[0.04] border border-gov-forest/15 p-4 flex gap-3'>
        <Info size={16} className='text-gov-forest dark:text-emerald-100 mt-0.5 shrink-0' />
        <div className='text-sm text-gov-dark/85 dark:text-white/85 leading-relaxed'>
          <strong className='text-gov-dark dark:text-white'>What each number counts.</strong>{' '}
          The CBK figure is Central-Government debt — loans Treasury owes
          directly. IMF's figure is General-Government, the measure
          credit-rating agencies and IMF Article IV use: it adds{' '}
          <strong>
            county debt, state-owned enterprise guarantees, pension arrears,
            and pending bills
          </strong>
          .{' '}
          {gap != null && gap > 0 && gap >= 1e12 ? (
            <>
              The{' '}
              <span className='font-semibold text-gov-dark dark:text-white'>
                ~{fmtT(gap)} gap
              </span>{' '}
              is public debt Kenyans will pay for — it&apos;s just not on
              Treasury&apos;s preferred scorecard.
            </>
          ) : gap != null && gap > 0 ? (
            <>
              For Kenya the gap is modest — about{' '}
              <span className='font-semibold text-gov-dark dark:text-white'>
                {fmtT(gap)}
              </span>
              . That&apos;s a good sign: county and SOE exposures off
              Treasury&apos;s book are smaller here than in many peer
              economies. The number to watch is whether the gap
              <em> widens</em> over time as pending bills and guarantees
              accumulate.
            </>
          ) : null}
        </div>
      </div>
    </motion.section>
  );
}
