'use client';

import { COUNTY_SPENDING_TARGET } from '@/components/transparency/moneyFlowPresentation';
import { countyBudget, countyDebt, countyPopulation } from '@/lib/countyFigures';
import { evidenceUrl, qualificationMessageKey, type FigureQualification } from '@/lib/evidence/qualification';
import { financialHealthBand } from '@/lib/counties/financialHealth';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_EXPLORER_MESSAGES } from '@/lib/i18n/messages/countyExplorer';
import type { County } from '@/types';
import Link from 'next/link';
import { useState } from 'react';
import { comparisonHref, MAX_COMPARE_COUNTIES } from './compare/ledgerData';
import styles from './CountyExperience.module.css';

export type CountySortField = 'name' | 'population' | 'health' | 'budget' | 'utilization' | 'debt';

const periodKey = (period: string | undefined) => typeof period === 'string' ? period.trim().replace(/^FY\s*/i, '') : '';

function matchesTotal(q: FigureQualification, county: County, fiscalYear: string) {
  const identity = q.identity;
  const category = identity?.dimensions?.category;
  return identity?.geography === `${county.name} County` &&
    periodKey(identity.period) === periodKey(fiscalYear) &&
    typeof category === 'string' && category.trim().toLowerCase() === 'total' && !identity.dimensions.subcategory;
}

function usableCobAmount(q: FigureQualification | undefined, measure: string) {
  if (!q) return false;
  const grade = qualificationMessageKey(q);
  const url = evidenceUrl(q.source_url);
  return q.identity?.measure === measure && q.identity?.basis === 'actual' && q.identity?.unit === 'KES' &&
    q.publisher === 'Controller of Budget' && url != null && /^https:\/\/(www\.)?cob\.go\.ke\//.test(url) &&
    (grade === 'evidence.status.verified' ||
      (grade === 'evidence.status.qualified' && q.reason === 'historical_source_not_value_checked'));
}

/** The list's rate can be a legacy zero for missing expenditure. A sourced Total distinguishes it. */
export function publishedSpendingRate(county: County, fiscalYear?: string): number | undefined {
  const rate = county.budgetUtilization;
  const allocation = countyBudget(county);
  if (!fiscalYear || !periodKey(fiscalYear) || county.budgetSource === 'cra_model' || county.budgetSource === 'mixed' ||
    allocation == null || !Number.isFinite(allocation) || allocation <= 0 ||
    rate == null || !Number.isFinite(rate) || rate < 0) return undefined;

  const totals = Object.values(county.figureQualifications?.budget_lines ?? {}).filter(({ allocated_amount, actual_spent }) =>
    (allocated_amount && matchesTotal(allocated_amount, county, fiscalYear)) ||
    (actual_spent && matchesTotal(actual_spent, county, fiscalYear)));
  if (totals.length !== 1) return undefined;
  const { allocated_amount: budget, actual_spent: spent } = totals[0];
  return budget && spent && matchesTotal(budget, county, fiscalYear) && matchesTotal(spent, county, fiscalYear) &&
    usableCobAmount(budget, 'allocated_amount') && usableCobAmount(spent, 'actual_spent') &&
    budget.identity.entity_id != null && budget.identity.entity_id === spent.identity.entity_id &&
    budget.source_document_id != null && budget.source_document_id === spent.source_document_id && budget.source_url === spent.source_url
    ? rate : undefined;
}

function measuredValue(county: County, sort: CountySortField, fiscalYear?: string) {
  switch (sort) {
    case 'name':
    case 'utilization': return publishedSpendingRate(county, fiscalYear);
    case 'budget': return countyBudget(county);
    case 'debt': return countyDebt(county);
    case 'population': return countyPopulation(county);
    case 'health': return financialHealthBand(county.financial_health_score) ? county.financial_health_score : undefined;
  }
}

function formatMeasurement(value: number, sort: CountySortField, formatKes: (value: number) => string) {
  if (sort === 'name' || sort === 'utilization') return `${value.toFixed(1)}%`;
  if (sort === 'health') return `${value.toFixed(1)}/100`;
  if (sort === 'population') return value.toLocaleString('en-KE');
  return `KES ${formatKes(value)}`;
}

export function countyRecordHref(countyId: string, fiscalYear?: string) {
  return `/counties/${countyId}${fiscalYear ? `?fy=${encodeURIComponent(fiscalYear)}` : ''}`;
}

export default function MobileCountyRanking({ counties, paged, firstRank, sort, fiscalYear, formatKes }: {
  counties: County[];
  paged: County[];
  firstRank: number;
  sort: CountySortField;
  fiscalYear?: string;
  formatKes: (value: number) => string;
}) {
  const { t, lang } = useLang();
  const copy = (key: keyof typeof COUNTY_EXPLORER_MESSAGES) => COUNTY_EXPLORER_MESSAGES[key][lang];
  const [selected, setSelected] = useState<Array<Pick<County, 'id' | 'name'>>>([]);
  const spending = sort === 'utilization' || sort === 'name';
  const comparable = spending && /^\d{4}\/\d{2}$/.test(periodKey(fiscalYear));
  const values = counties.flatMap(county => {
    const value = measuredValue(county, sort, fiscalYear);
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? [[county.id, value] as const] : [];
  });
  const range = spending || sort === 'health' ? 100 : Math.max(0, ...values.map(([, value]) => value));
  const measurements = new Map(values);

  function toggleCounty(county: County) {
    setSelected(current => current.some(item => item.id === county.id)
      ? current.filter(item => item.id !== county.id)
      : current.length < MAX_COMPARE_COUNTIES ? [...current, { id: county.id, name: county.name }] : current);
  }

  const selectionCount = copy('counties.rankings.compare_selected').replace('{count}', String(selected.length));
  const selectionLimit = copy('counties.rankings.compare_limit').replace('{count}', String(MAX_COMPARE_COUNTIES));

  return (
    <div className={styles.mobileRanking}>
      {paged.length > 0 && <>
        {(sort === 'budget' || spending) && fiscalYear && <p className='mb-2 text-sm text-neutral-muted'>
          {spending ? copy('counties.rankings.spending_period').replace('{period}', fiscalYear) : fiscalYear}
        </p>}
        <ol aria-label={t('counties.rankings.title')} start={firstRank} role='list' className='border-y border-neutral-border'>
          {paged.map((county, index) => {
            const value = measurements.get(county.id);
            const available = value != null;
            const ranked = available || sort === 'name';
            const low = comparable && available && value < COUNTY_SPENDING_TARGET;
            const checked = selected.some(item => item.id === county.id);
            const note = low ? copy('counties.rankings.below_target')
              : sort === 'budget' && available && county.budgetSource === 'cra_model' ? copy('counties.rankings.modelled_amount') : null;
            return (
              <li key={county.id} className={styles.rankingRow}>
                <Link href={countyRecordHref(county.id, fiscalYear)} className={styles.rankingCounty}>
                  <span className='text-xs font-normal text-neutral-muted tabular-nums'>
                    {ranked ? <><span className='sr-only'>{copy('counties.rankings.rank')} </span>{firstRank + index}</> : '—'}
                  </span>
                  <span className='min-w-0 font-semibold break-words'>{county.name}</span>
                  <span className={`font-semibold tabular-nums ${available ? 'font-display text-audit-heading' : 'text-sm'} ${low ? 'text-signal-caution' : ''}`}>
                    {available ? formatMeasurement(value, sort, formatKes) : copy('counties.rankings.measure_unavailable')}
                  </span>
                </Link>
                <div className={styles.rankingMeasure}>
                  {available && <div aria-hidden='true' className='h-1.5 rounded bg-surface-sunken'>
                    <div className={`h-full rounded ${low ? 'bg-signal-caution' : comparable ? 'bg-signal-good' : 'bg-signal-context'}`}
                      style={{ width: `${range > 0 ? Math.min(100, value / range * 100) : 0}%` }} />
                  </div>}
                  {note && <span className={low ? 'text-xs font-semibold text-signal-caution' : 'text-xs text-neutral-muted'}>{note}</span>}
                </div>
                <label className={styles.rankingCompare}>
                  <input type='checkbox' className='h-4 w-4 accent-gov-sage' checked={checked}
                    disabled={!checked && selected.length >= MAX_COMPARE_COUNTIES}
                    onChange={() => toggleCounty(county)} aria-label={copy('counties.rankings.compare_county').replace('{county}', county.name)} />
                  {copy('counties.rankings.compare')}
                </label>
              </li>
            );
          })}
        </ol>
      </>}
      <p className='sr-only' role='status'>{selected.length ? selectionCount : ''}</p>
      {selected.length >= 2 && <aside aria-label={copy('counties.rankings.compare_selection')} className={styles.rankingTray}>
        <div className='min-w-0 break-words text-sm'>
          <strong>{selectionCount}</strong> · {selected.map(item => item.name).join(', ')}
          {selected.length === MAX_COMPARE_COUNTIES && <p className='text-xs text-neutral-muted'>{selectionLimit}</p>}
        </div>
        <Link href={comparisonHref(selected.map(item => item.id))} className='audit-control shrink-0'>
          {copy('counties.rankings.compare')}
        </Link>
      </aside>}
    </div>
  );
}
