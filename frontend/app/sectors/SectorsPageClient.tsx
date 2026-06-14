/**
 * National Sector Spending
 *
 * Rolls up every county's latest executed budget into a canonical set of
 * sectors (Health, Education, Roads, Water, ...) so you can see at a
 * glance where Kenya's devolved budgets are flowing — and which sectors
 * are executing well vs. sitting on unspent allocations.
 */
'use client';

import ModelledDataNote from '@/components/ModelledDataNote';
import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Briefcase,
  GraduationCap,
  Hammer,
  Leaf,
  Loader2,
  Sprout,
  Truck,
  Users,
  Building2,
  Droplets,
  Info,
} from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

// Map backend sector labels → translation keys
const SECTOR_KEY: Record<string, TranslationKey> = {
  Health: 'sectors.health',
  Education: 'sectors.education',
  'Roads & Infrastructure': 'sectors.roads',
  'Water & Sanitation': 'sectors.water',
  Agriculture: 'sectors.agriculture',
  Environment: 'sectors.environment',
  'Trade & Industry': 'sectors.trade',
  'Social Services': 'sectors.social',
  Administration: 'sectors.admin',
  Other: 'sectors.other',
};

interface SectorEntry {
  sector: string;
  allocated: number;
  spent: number;
  utilization_pct: number;
  county_count: number;
  top_counties: Array<{ county: string; allocated: number; spent: number }>;
}

interface SectorResponse {
  total_allocated: number;
  total_spent: number;
  counties_reporting: number;
  sectors: SectorEntry[];
  fiscal_year?: string | null;
  is_partial_year?: boolean;
  is_projected?: boolean;
  source?: string;
}

function fmtKES(n: number): string {
  if (n >= 1e12) return `KES ${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `KES ${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `KES ${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}

const SECTOR_ICON: Record<string, typeof Activity> = {
  Health: Activity,
  Education: GraduationCap,
  'Roads & Infrastructure': Hammer,
  'Water & Sanitation': Droplets,
  Agriculture: Sprout,
  Environment: Leaf,
  'Trade & Industry': Truck,
  'Social Services': Users,
  Administration: Building2,
  Other: Briefcase,
};

const SECTOR_COLOR: Record<string, string> = {
  Health: 'from-rose-500 to-rose-600',
  Education: 'from-blue-500 to-blue-600',
  'Roads & Infrastructure': 'from-amber-500 to-amber-600',
  'Water & Sanitation': 'from-sky-500 to-sky-600',
  Agriculture: 'from-emerald-500 to-emerald-600',
  Environment: 'from-teal-500 to-teal-600',
  'Trade & Industry': 'from-purple-500 to-purple-600',
  'Social Services': 'from-pink-500 to-pink-600',
  Administration: 'from-gray-500 to-gray-600',
  Other: 'from-slate-400 to-slate-500',
};

function utilClass(pct: number): string {
  if (pct >= 85) return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (pct >= 60) return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-rose-700 bg-rose-50 border-rose-200';
}

export default function SectorsPage() {
  const { t } = useLang();
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery<SectorResponse>({
    queryKey: ['sectors', 'spending'],
    queryFn: async () => (await api.get<SectorResponse>('/sectors/spending')).data,
    staleTime: 10 * 60 * 1000,
  });

  const translateSector = (raw: string) => {
    const key = SECTOR_KEY[raw];
    return key ? t(key) : raw;
  };

  const maxSpend = useMemo(
    () => (data?.sectors || []).reduce((m, s) => Math.max(m, s.spent), 0),
    [data]
  );

  const overallUtil =
    data && data.total_allocated > 0
      ? (data.total_spent / data.total_allocated) * 100
      : 0;

  return (
    <PageShell
      title={t('sectors.title')}
      subtitle={t('sectors.subtitle')}
      back={{ href: '/', label: t('common.home') }}>
      <div className='space-y-6'>
        {/* Provenance: county financials are modelled estimates, and an
            in-progress fiscal year is projected — not final actuals (§2.10). */}
        <ModelledDataNote />
        {data?.is_projected && (
          <div
            role='note'
            className='flex items-start gap-2.5 rounded-lg border border-sky-300/70 bg-sky-50 px-4 py-3 text-sm dark:border-sky-700/50 dark:bg-sky-950/30'>
            <Info className='mt-0.5 h-4 w-4 flex-shrink-0 text-sky-600 dark:text-sky-400' />
            <p className='leading-snug text-sky-900/90 dark:text-sky-100/90'>
              {data?.fiscal_year ? `FY ${data.fiscal_year.replace('FY', '').trim()}: ` : ''}
              {t('sectors.projected_note')}
            </p>
          </div>
        )}
        {/* Top-line strip */}
        <div className='grid grid-cols-1 sm:grid-cols-3 gap-4'>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              {t('sectors.total_allocated')}
            </div>
            <div className='text-3xl font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
              {fmtKES(data?.total_allocated || 0)}
            </div>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-1'>
              {t('sectors.total_allocated_sub').replace('{n}', String(data?.counties_reporting || 0))}
            </div>
          </div>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              {t('sectors.total_executed')}
            </div>
            <div className='text-3xl font-bold text-emerald-700 tabular-nums'>
              {fmtKES(data?.total_spent || 0)}
            </div>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-1'>{t('sectors.total_executed_sub')}</div>
          </div>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              {t('sectors.execution_rate')}
            </div>
            <div className='text-3xl font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
              {overallUtil.toFixed(1)}%
            </div>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-1'>{t('sectors.execution_rate_sub')}</div>
          </div>
        </div>

        {/* Loading / error */}
        {isLoading && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 flex items-center justify-center gap-3 text-gray-500 dark:text-neutral-muted/80'>
            <Loader2 className='animate-spin' size={18} />
            <span>{t('sectors.loading')}</span>
          </div>
        )}
        {error && (
          <div className='bg-rose-50 border border-rose-200 rounded-xl p-4 text-rose-800 text-sm'>
            {t('sectors.error')}
          </div>
        )}

        {/* Sector cards */}
        {!isLoading && !error && data && (
          <div className='space-y-3'>
            {data.sectors.map((s) => {
              const Icon = SECTOR_ICON[s.sector] || Briefcase;
              const color = SECTOR_COLOR[s.sector] || 'from-gray-400 to-gray-500';
              const sharePct = maxSpend > 0 ? (s.spent / maxSpend) * 100 : 0;
              const isOpen = expanded === s.sector;
              return (
                <article
                  key={s.sector}
                  className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border overflow-hidden hover:border-gov-sage/40 hover:shadow-md transition-all'>
                  <button
                    type='button'
                    onClick={() => setExpanded(isOpen ? null : s.sector)}
                    className='w-full text-left p-5'>
                    <div className='flex items-center gap-4 flex-wrap'>
                      <div
                        className={`w-11 h-11 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center text-white shrink-0 shadow-sm`}>
                        <Icon size={20} />
                      </div>
                      <div className='flex-1 min-w-[180px]'>
                        <div className='flex items-center gap-2 flex-wrap'>
                          <h2 className='text-base font-bold text-gray-900 dark:text-neutral-text'>{translateSector(s.sector)}</h2>
                          <span className='text-xs text-gray-500 dark:text-neutral-muted/80'>
                            · {s.county_count} {t('sectors.counties_count')}
                          </span>
                        </div>
                        <div className='mt-2 h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                          <div
                            className={`h-full bg-gradient-to-r ${color}`}
                            style={{ width: `${Math.min(sharePct, 100)}%` }}
                          />
                        </div>
                      </div>
                      <div className='text-right'>
                        <div className='text-xl font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                          {fmtKES(s.spent)}
                        </div>
                        <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>
                          {t('sectors.of_label')} {fmtKES(s.allocated)}
                        </div>
                      </div>
                      <div
                        className={`inline-flex items-center text-xs font-semibold px-2 py-1 rounded-full border ${utilClass(s.utilization_pct)}`}>
                        {s.utilization_pct.toFixed(0)}% {t('sectors.executed_suffix')}
                      </div>
                    </div>
                  </button>

                  {isOpen && (
                    <div className='border-t border-gray-100 dark:border-neutral-border bg-gray-50/60 dark:bg-surface-elevated/70 px-5 py-4'>
                      <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-3'>
                        {t('sectors.top_counties').replace('{sector}', translateSector(s.sector))}
                      </div>
                      <div className='space-y-2'>
                        {s.top_counties.map((c, i) => {
                          const cUtil =
                            c.allocated > 0 ? (c.spent / c.allocated) * 100 : 0;
                          return (
                            <div
                              key={c.county}
                              className='flex items-center gap-3 text-sm'>
                              <div className='w-6 text-xs font-bold text-gray-400 dark:text-neutral-muted/80 tabular-nums'>
                                #{i + 1}
                              </div>
                              <Link
                                href={`/counties?search=${encodeURIComponent(c.county)}`}
                                className='w-32 font-semibold text-gray-800 dark:text-neutral-text hover:text-gov-forest dark:text-emerald-100 hover:underline truncate'>
                                {c.county}
                              </Link>
                              <div className='flex-1 h-1.5 bg-gray-200 dark:bg-surface-sunken rounded-full overflow-hidden'>
                                <div
                                  className={`h-full bg-gradient-to-r ${color}`}
                                  style={{
                                    width: `${Math.min(s.top_counties[0]?.spent ? (c.spent / s.top_counties[0].spent) * 100 : 0, 100)}%`,
                                  }}
                                />
                              </div>
                              <div className='w-24 text-right font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                                {fmtKES(c.spent)}
                              </div>
                              <div className='w-14 text-right text-xs text-gray-500 dark:text-neutral-muted/80 tabular-nums'>
                                {cUtil.toFixed(0)}%
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}

        {/* Methodology */}
        <div className='bg-gov-forest/5 border border-gov-forest/20 rounded-xl p-5'>
          <div className='text-sm text-gray-700 dark:text-neutral-muted leading-relaxed'>
            <p className='font-semibold text-gray-900 dark:text-neutral-text mb-1'>{t('sectors.methodology.title')}</p>
            <p>{t('sectors.methodology.body')}</p>
            {data?.source && (
              <p className='mt-2 text-xs text-gray-500 dark:text-neutral-muted/80'>
                {t('sectors.source_label')}: {data.source}
                {data?.fiscal_year ? ` · FY ${data.fiscal_year.replace('FY', '').trim()}` : ''}
              </p>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  );
}
