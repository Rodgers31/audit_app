'use client';

import CountyBorrowingNote from '@/components/county/CountyBorrowingNote';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import styles from '../../CountyExperience.module.css';

import { useLang } from '@/lib/i18n/LangProvider';
import UnaccountedFindings from '@/components/accountability/UnaccountedFindings';
import type { TranslationKey } from '@/lib/i18n/messages';
import { CountyComprehensive, OfficialSource } from '@/types';
import { ExternalLink } from 'lucide-react';
import React from 'react';
import { ABSENT, fmtKES, fmtLabel, fmtPop, pct } from '../shared';
import OverviewHighlights, { type OverviewDestination } from './OverviewHighlights';
import { COUNTY_OVERVIEW_MESSAGES } from '@/lib/i18n/messages/countyDetail';
import KPI from './KPI';
import { countyRevenueNotes } from '@/lib/counties/revenueNotes';

/* ═══════════ Officials Card — Who Runs This County ═══════════ */
/**
 * Only names a publisher supplied (#231). Both come from the Council of
 * Governors, read on every nightly seed; the API withholds a name that has
 * no source behind it.
 *
 * This card used to read party, term, deputy governor, CEC Finance, speaker
 * and website from a hand-typed `lib/data/county-officials.ts`. For Meru it
 * put the sitting governor beside his impeached predecessor's party and term,
 * and listed him again as deputy. Rows with no publisher were removed, not
 * left as "Not yet published": nothing on the nightly will ever fill them.
 */
function OfficialsCard({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const sources = data.officials_source;
  const rows: Array<{
    role: 'governor' | 'deputy_governor';
    name: string | null;
  }> = [
    { role: 'governor', name: data.governor || null },
    { role: 'deputy_governor', name: data.deputy_governor || null },
  ];
  // One link per distinct source page; both roles usually cite the same
  // publisher but two different pages.
  const cited = rows
    .map((r) => ({ role: r.role, src: sources?.[r.role] }))
    .filter((c): c is { role: typeof c.role; src: OfficialSource } => !!c.src)
    .filter((c, i, all) => all.findIndex((o) => o.src.source_url === c.src.source_url) === i);

  return (
    <section className={styles.section} aria-label={t('county.officials.card_title')}>
      <div className='mb-3'>
        <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text'>
          {t('county.officials.card_title')}
        </h3>
        <p className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
          {t('county.officials.card_subtitle')}
        </p>
      </div>
      <div className='grid grid-cols-1 sm:grid-cols-2 gap-3'>
        {rows.map((r) => (
          <div
            key={r.role}
            title={t(`county.officials.desc.${r.role}` as TranslationKey)}
            className={styles.official}>
            <div className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
              {t(`county.officials.title.${r.role}` as TranslationKey)}
            </div>
            <div
              className={`text-sm font-semibold mt-0.5 ${r.name ? 'text-gray-900 dark:text-neutral-text' : 'text-gray-400 dark:text-neutral-muted/80 italic'}`}>
              {r.name || t('county.officials.not_listed')}
            </div>
          </div>
        ))}
      </div>
      {cited.length > 0 && (
        <p className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-3'>
          {t('county.officials.source')}:{' '}
          {cited.map(({ role, src: s }, i) => (
            <React.Fragment key={s.source_url}>
              {i > 0 && ' · '}
              <a
                href={s.source_url}
                target='_blank'
                rel='noopener noreferrer'
                className='text-gov-forest dark:text-emerald-100 hover:underline inline-flex items-center gap-1'>
                {s.publisher || new URL(s.source_url).hostname} —{' '}
                {t(`county.officials.title.${role}` as TranslationKey)}
                <ExternalLink size={10} />
              </a>
              {s.fetched_at && (
                <span>
                  {' '}
                  ({t('county.officials.fetched')} {s.fetched_at.slice(0, 10)})
                </span>
              )}
            </React.Fragment>
          ))}
        </p>
      )}
    </section>
  );
}

/* ═══════════ Tab: Overview ═══════════ */
export default function OverviewTab({ data, onOpenTab }: {
  data: CountyComprehensive;
  onOpenTab?: (tab: OverviewDestination) => void;
}) {
  const { lang } = useLang();
  return (
    <div className='space-y-4'>
      <OverviewHighlights data={data} onOpenTab={onOpenTab} />
      <details className='min-w-0 max-w-3xl border-y border-neutral-border'>
        <summary className='min-h-11 cursor-pointer py-3 text-sm font-semibold text-neutral-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2'>
          {COUNTY_OVERVIEW_MESSAGES.more[lang]}
        </summary>
        <AdditionalCountyDetails data={data} />
      </details>
    </div>
  );
}

function AdditionalCountyDetails({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { demographics, economic_profile, debt, missing_funds, revenue } = data;

  return (
    <div className='space-y-3 pb-3'>
      {data.budget.figure_qualifications && <FigureEvidence label='county budget observations'
        labelKey='evidence.label.county_budget' rows={data.budget.figure_qualifications} table='budget_lines' />}
      <section className={styles.section}>
        <h3 className='mb-2 text-base font-semibold'>{t('county.overview.debt_position')}</h3>
        <CountyBorrowingNote balance={debt.total_debt} absentReason={debt.total_debt_absent_reason}
          coverage={debt.debt_source_coverage} asAt={debt.debt_as_at} />
        {debt.total_debt != null && (
          <dl className='space-y-2 text-sm'>
            <div><dt>{t('county.overview.debt_total')}</dt><dd className='font-semibold'>{fmtKES(debt.total_debt)}</dd></div>
            {debt.debt_to_budget_ratio != null && (
              <div><dt>{t('county.overview.debt_to_budget')}</dt><dd className='font-semibold'>{pct(debt.debt_to_budget_ratio)}</dd></div>
            )}
          </dl>
        )}
      </section>
      {/* Missing funds banner */}
      <UnaccountedFindings cases={missing_funds.cases} />

      {economic_profile.latest_gcp && <div className={styles.section}><h3 className='font-semibold'>{t('evidence.county.gcp_title')} · {economic_profile.latest_gcp.year}{economic_profile.latest_gcp.quarter ? ` · ${economic_profile.latest_gcp.quarter}` : ''}</h3><p>{economic_profile.latest_gcp.gdp_value == null ? t('evidence.page.not_published') : `${economic_profile.latest_gcp.currency} ${economic_profile.latest_gcp.gdp_value.toLocaleString('en-KE')}`}</p><FigureEvidence label='gross county product' labelKey='evidence.label.gross_county_product' qualifications={economic_profile.latest_gcp.qualifications} table='gdp_data' recordId={economic_profile.latest_gcp.record_id} /></div>}
      {economic_profile.latest_poverty && <div className={styles.section}><h3 className='font-semibold'>{t('evidence.county.poverty_title')} · {economic_profile.latest_poverty.year}</h3><p>{t('evidence.county.headcount')}: {economic_profile.latest_poverty.poverty_headcount_rate == null ? t('evidence.page.not_published') : `${economic_profile.latest_poverty.poverty_headcount_rate}%`}</p><p>{t('evidence.county.extreme')}: {economic_profile.latest_poverty.extreme_poverty_rate == null ? t('evidence.page.not_published') : `${economic_profile.latest_poverty.extreme_poverty_rate}%`}</p><p>{t('evidence.county.gini')}: {economic_profile.latest_poverty.gini_coefficient ?? t('evidence.page.not_published')}</p><FigureEvidence label='poverty observations' labelKey='evidence.label.poverty_observations' qualifications={economic_profile.latest_poverty.qualifications} table='poverty_indices' recordId={economic_profile.latest_poverty.record_id} /></div>}
      {/* About this county */}
      <div className={styles.section}>
        <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-3'>
          {t('county.profile.title')}
        </h3>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-6'>
          <KPI
            label={t('county.profile.population')}
            value={fmtPop(demographics.population)}
            sub={
              demographics.population_year
                ? `${t('county.overview.kpi.census')} ${demographics.population_year}`
                : undefined
            }
            accent='text-blue-700'
          />
          <KPI
            label={t('county.profile.governor')}
            value={data.governor || t('county.overview.kpi.na')}
            accent='text-purple-700'
          />
          <KPI
            label={t('county.profile.economic_base')}
            value={
              economic_profile.economic_base ? fmtLabel(economic_profile.economic_base) : ABSENT
            }
            accent='text-emerald-700'
          />
          <KPI
            label={
              revenue.total_revenue_basis === 'cash_receipts_including_opening_balance'
                ? t('county.revenue.cash_and_opening_balance')
                : t('county.overview.kpi.total_revenue')
            }
            value={fmtKES(revenue.total_revenue)}
            sub={countyRevenueNotes(revenue, fmtKES, t).join(' · ') || undefined}
            accent='text-green-700'
          />
        </div>

        {economic_profile.major_issues.length > 0 && (
          <div className='mt-4 pt-4 border-t border-gray-100 dark:border-neutral-border'>
            <div className='text-xs font-semibold text-gray-500 dark:text-neutral-muted/80 uppercase tracking-wider mb-2'>
              {t('county.overview.key_challenges')}
            </div>
            <div className='flex flex-wrap gap-2'>
              {economic_profile.major_issues.map((issue, i) => (
                <span
                  key={i}
                  className='text-xs bg-amber-50 text-amber-800 border border-amber-200 rounded-full px-2.5 py-1'>
                  {issue}
                </span>
              ))}
            </div>
            <p className='mt-2 text-[11px] text-gray-400 dark:text-neutral-muted/80 italic'>
              {economic_profile.major_issues_source
                ? t('county.overview.challenges_oag_note')
                : t('county.overview.challenges_generic_note')}
            </p>
          </div>
        )}
      </div>

      {/* Who Runs This County — named officials */}
      <OfficialsCard data={data} />

    </div>
  );
}
