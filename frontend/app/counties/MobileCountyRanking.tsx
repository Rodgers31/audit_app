'use client';

import { formatSpendingRate, publishedSpendingRate, spendingBand } from '@/lib/counties/spendingRate';
import { countyBudget, countyDebt, countyPopulation } from '@/lib/countyFigures';
import { financialHealthBand } from '@/lib/counties/financialHealth';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_EXPLORER_MESSAGES } from '@/lib/i18n/messages/countyExplorer';
import type { County } from '@/types';
import Link from 'next/link';
import { useState } from 'react';
import { comparisonHref, MAX_COMPARE_COUNTIES } from './compare/ledgerData';
import styles from './CountyExperience.module.css';
import { formatPerPerson, type PerPersonMeasure } from './CountyPerPerson';

export type CountySortField = 'name' | 'population' | 'health' | 'budget' | 'utilization' | 'debt';

export { publishedSpendingRate };

function measuredValue(county: County, sort: CountySortField, readSpendingRate: (county: County) => number | undefined) {
  switch (sort) {
    case 'name':
    case 'utilization': return readSpendingRate(county);
    case 'budget': return countyBudget(county);
    case 'debt': return countyDebt(county);
    case 'population': return countyPopulation(county);
    case 'health': return financialHealthBand(county.financial_health_score) ? county.financial_health_score : undefined;
  }
}

function formatMeasurement(value: number, sort: CountySortField, formatKes: (value: number) => string) {
  if (sort === 'name' || sort === 'utilization') return formatSpendingRate(value);
  if (sort === 'health') return `${value.toFixed(1)}/100`;
  if (sort === 'population') return value.toLocaleString('en-KE');
  return `KES ${formatKes(value)}`;
}

export function countyRecordHref(countyId: string, fiscalYear?: string) {
  return `/counties/${countyId}${fiscalYear ? `?fy=${encodeURIComponent(fiscalYear)}` : ''}`;
}

export default function MobileCountyRanking({ counties, paged, firstRank, sort, fiscalYear, formatKes, perPerson, readSpendingRate = county => publishedSpendingRate(county, fiscalYear) }: {
  counties: County[];
  paged: County[];
  firstRank: number;
  sort: CountySortField;
  fiscalYear?: string;
  formatKes: (value: number) => string;
  perPerson?: PerPersonMeasure;
  readSpendingRate?: (county: County) => number | undefined;
}) {
  const { t, lang } = useLang();
  const copy = (key: keyof typeof COUNTY_EXPLORER_MESSAGES) => COUNTY_EXPLORER_MESSAGES[key][lang];
  const [selected, setSelected] = useState<Array<Pick<County, 'id' | 'name'>>>([]);
  const spending = !perPerson && (sort === 'utilization' || sort === 'name');
  const values = counties.flatMap(county => {
    const value = perPerson ? perPerson.amounts.get(county.id)?.value : measuredValue(county, sort, readSpendingRate);
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? [[county.id, value] as const] : [];
  });
  const range = perPerson?.maximum ?? (spending || sort === 'health' ? 100 : Math.max(0, ...values.map(([, value]) => value)));
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
        {!perPerson && (sort === 'budget' || spending) && fiscalYear && <p className='mb-2 text-sm text-neutral-muted'>
          {spending ? copy('counties.rankings.spending_period').replace('{period}', fiscalYear) : fiscalYear}
        </p>}
        <ol aria-label={t('counties.rankings.title')} start={firstRank} role='list' className='border-y border-neutral-border'>
          {paged.map((county, index) => {
            const value = measurements.get(county.id);
            const available = value != null;
            const ranked = available || (!perPerson && sort === 'name');
            const band = spending ? spendingBand(value, fiscalYear) : undefined;
            const label = available
              ? (perPerson ? formatPerPerson(value) : formatMeasurement(value, sort, formatKes))
              : t(perPerson
                ? 'counties.per_person.unavailable'
                : band ? 'counties.spending.unavailable' : 'counties.rankings.measure_unavailable');
            const checked = selected.some(item => item.id === county.id);
            const note = band && available ? copy(`counties.spending.${band}`)
              : !perPerson && sort === 'budget' && available && county.budgetSource === 'cra_model' ? copy('counties.rankings.modelled_amount') : null;
            return (
              <li key={county.id} className={styles.rankingRow} data-spending-band={band}>
                <Link href={countyRecordHref(county.id, fiscalYear)} className={styles.rankingCounty}>
                  <span className='text-xs font-normal text-neutral-muted tabular-nums'>
                    {ranked ? <><span className='sr-only'>{copy('counties.rankings.rank')} </span>{firstRank + index}</> : '—'}
                  </span>
                  <span className='min-w-0 font-semibold break-words'>{county.name}</span>
                  <span className={`font-semibold tabular-nums ${available ? 'font-display text-audit-heading' : 'text-sm'}`}>
                    {label}
                  </span>
                </Link>
                <div className={styles.rankingMeasure}>
                  {available && <div aria-hidden='true' className='h-1.5 rounded bg-surface-sunken'>
                    <div className='h-full rounded bg-signal-context'
                      style={{ width: `${range > 0 ? Math.min(100, value / range * 100) : 0}%`, backgroundColor: perPerson ? 'var(--county-per-person-4)' : band ? 'var(--county-spending-fill)' : undefined }} />
                  </div>}
                  {note && <span className='text-xs text-neutral-muted' style={{ color: band ? 'var(--county-spending-ink)' : undefined }}>{note}</span>}
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
