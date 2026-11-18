'use client';

import { budgetProvenanceKey } from '@/components/ModelledDataNote';
import { COUNTY_SPENDING_TARGET } from '@/components/transparency/moneyFlowPresentation';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import ResponsiveTable from '@/components/ui/ResponsiveTable';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_COMPARE_MESSAGES as messages } from '@/lib/i18n/messages/countyCompare';
import { fmtKES } from '@/lib/utils';
import { ChevronDown } from 'lucide-react';
import Link from 'next/link';
import type { KeyboardEvent, ReactNode } from 'react';
import CompareDebtInfo from './CompareDebtInfo';
import CompareShare from './CompareShare';
import {
  budgetAmount, budgetComparisonBasis, budgetMoney, budgetPeriod, comparisonHref, comparisonRanks,
  debtAmount, debtComparisonBasis, publishedFindingCount, reported, spentAmount, utilization,
  type CountySummary,
} from './ledgerData';

type Measure = {
  id: string;
  name: string;
  hint?: string;
  amount?: (county: CountySummary) => number | null;
  display: (value: number, county: CountySummary) => string;
  basis?: (county: CountySummary) => string | undefined;
  badgeClass?: (kind: 'highest' | 'lowest', amount: number) => string;
  titleExtra?: ReactNode;
  showPeriod?: boolean;
};

const number = (value: number) => value.toLocaleString('en-KE');
const percent = (value: number) => `${value.toFixed(1)}%`;

function scrollLedger(event: KeyboardEvent<HTMLDivElement>) {
  const { key, target } = event;
  if (key !== 'ArrowLeft' && key !== 'ArrowRight') return;
  if (!(target instanceof HTMLDivElement) || target.getAttribute('role') !== 'region') return;
  if (target.scrollWidth <= target.clientWidth) return;
  event.preventDefault();
  target.scrollLeft += key === 'ArrowRight' ? 112 : -112;
}

function LedgerTable({ counties, measures, title, header, linkNames }: {
  counties: CountySummary[];
  measures: Measure[];
  title: string;
  header: string;
  linkNames?: boolean;
}) {
  const { lang } = useLang();
  return (
    <div onKeyDown={scrollLedger}>
      <ResponsiveTable key={counties.length} className='min-w-0 rounded-md border border-neutral-border bg-surface-base'>
        <table className={`relative w-full table-fixed border-separate border-spacing-0 text-sm ${counties.length === 4 ? 'min-w-[34.25rem]' : ''} ${counties.length === 3 ? 'min-w-[27.25rem]' : ''}`}>
          <caption className='sr-only'>{title}</caption>
          <colgroup>
            <col className='w-[6.25rem] md:w-44' />
            {counties.map((county) => <col key={county.id} />)}
          </colgroup>
          <thead>
            <tr>
              <th scope='col' className='sticky left-0 z-10 border-b border-neutral-border bg-surface-sunken px-2 py-2 text-left font-semibold text-neutral-text [overflow-wrap:anywhere]'>{header}</th>
              {counties.map((county) => (
                <th key={county.id} scope='col' className='border-b border-neutral-border bg-surface-sunken px-2 py-1 text-right align-middle font-semibold [overflow-wrap:anywhere]'>
                  {linkNames ? (
                    <Link href={`/counties/${encodeURIComponent(county.id)}`}
                      className='flex min-h-11 min-w-11 items-center justify-end rounded px-0.5 text-neutral-text underline decoration-neutral-border underline-offset-2 hover:decoration-current focus-visible:outline-2 focus-visible:outline-gov-forest motion-reduce:transition-none dark:focus-visible:outline-emerald-100'>
                      <span className='min-w-0'>{county.name}</span>
                    </Link>
                  ) : county.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {measures.map((measure) => {
              const values = counties.map((county) => {
                const amount = measure.amount?.(county) ?? null;
                const display = amount === null ? '—' : measure.display(amount, county);
                return { amount, display, basis: measure.basis?.(county) };
              });
              const ranks = comparisonRanks(values);
              return (
                <tr key={measure.id} className='[&:last-child>*]:border-b-0'>
                  <th scope='row' className='sticky left-0 z-10 border-b border-neutral-border bg-surface-base px-2 py-1 text-left align-middle font-semibold [overflow-wrap:anywhere]'>
                    <div className='flex items-center gap-0.5'>
                      <span className='min-w-0'>{measure.name}</span>
                      {measure.titleExtra}
                    </div>
                    {measure.hint && <div className='mt-0.5 text-xs font-normal text-neutral-muted'>{measure.hint}</div>}
                  </th>
                  {values.map(({ amount, display }, index) => {
                    const county = counties[index];
                    const rank = ranks[index];
                    return (
                      <td key={county.id} className='relative border-b border-neutral-border px-2 py-2 text-right align-middle tabular-nums [overflow-wrap:anywhere]'>
                        {amount === null ? (
                          <><span aria-hidden='true'>—</span><span className='sr-only'>{messages.missing[lang]}</span></>
                        ) : (
                          <div className='flex flex-wrap items-baseline justify-end gap-x-1.5'>
                            <span className={rank ? 'font-semibold' : undefined}>{display}</span>
                            {rank && <span className={`text-xs font-semibold ${measure.badgeClass?.(rank, amount) ?? 'text-signal-context'}`}>{messages[rank][lang]}</span>}
                          </div>
                        )}
                        {amount !== null && measure.showPeriod && budgetPeriod(county)?.label && (
                          <span className='block text-xs text-neutral-muted'>{budgetPeriod(county)?.label}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </ResponsiveTable>
    </div>
  );
}

export default function CompareLedger({ counties }: { counties: CountySummary[] }) {
  const { lang, t } = useLang();
  const key = budgetProvenanceKey(counties.map((county) => county.budget_source));
  const periods = counties.filter((county) => budgetAmount(county) !== null).map(budgetPeriod);
  const knownPeriod = periods[0];
  const commonPeriod = knownPeriod?.label && periods.every((period) => period?.from === knownPeriod.from && period.to === knownPeriod.to)
    ? knownPeriod.label
    : null;
  const mainMeasures: Measure[] = [
    { id: 'budget', name: messages.budget[lang], amount: budgetAmount, display: budgetMoney, basis: budgetComparisonBasis, showPeriod: !commonPeriod },
    { id: 'execution', name: messages.spentRate[lang], amount: utilization, display: percent, basis: budgetComparisonBasis,
      badgeClass: (rank, amount) => rank === 'highest' && amount >= COUNTY_SPENDING_TARGET ? 'text-signal-good' : 'text-signal-context' },
    { id: 'debt', name: t('compare.row.debt'), amount: debtAmount, display: fmtKES, basis: debtComparisonBasis, titleExtra: <CompareDebtInfo counties={counties} /> },
    { id: 'findings', name: messages.findings[lang], amount: publishedFindingCount, display: number },
    { id: 'serious', name: messages.seriousFindings[lang], display: number },
  ];
  const more: Measure[] = [
    { id: 'population', name: t('compare.row.population'), amount: (county) => reported(county.population), display: number },
    { id: 'per-capita', name: t('compare.row.per_capita'), hint: t('compare.row.per_capita_sub'), display: budgetMoney,
      amount: (county) => {
        const budget = budgetAmount(county);
        return budget !== null && county.population && county.population > 0 ? budget / county.population : null;
      } },
    { id: 'actual', name: t('compare.row.spent'), amount: spentAmount, display: budgetMoney, basis: budgetComparisonBasis },
    { id: 'dev', name: t('compare.row.dev_share'), hint: t('compare.row.dev_share_sub'), display: percent,
      amount: (county) => {
        const budget = budgetAmount(county);
        const development = reported(county.development_budget);
        return budget && development !== null ? development / budget * 100 : null;
      } },
    { id: 'bills', name: t('compare.row.pending_bills'), hint: t('compare.row.pending_bills_sub'), amount: (county) => reported(county.pending_bills), display: fmtKES },
    { id: 'health', name: t('compare.row.health_score'), hint: t('compare.row.health_score_sub'), amount: (county) => reported(county.financial_health_score), display: (value) => value.toFixed(0) },
  ];

  return (
    <div data-compare-ledger className='min-w-0 space-y-3'>
      <LedgerTable counties={counties} measures={mainMeasures} title={messages.table[lang]} header={commonPeriod || messages.measure[lang]} linkNames />
      <div className='space-y-1 rounded bg-surface-sunken p-3 text-sm text-neutral-text'>
        <p>{messages.readingNote[lang]}</p>
        <p>{messages.findingsScope[lang]}</p>
      </div>
      <CompareShare href={comparisonHref(counties.map((county) => county.id))} />
      <details className='group space-y-2'>
        <summary className='audit-control inline-flex cursor-pointer gap-2 motion-reduce:transition-none'>
          {messages.moreMeasures[lang]}
          <ChevronDown aria-hidden='true' size={16} className='group-open:rotate-180' />
        </summary>
        <LedgerTable counties={counties} measures={more} title={messages.moreMeasures[lang]} header={messages.measure[lang]} />
      </details>
      {key && <p role='note' className='text-sm text-neutral-muted'>{t(key)}</p>}
      <div className='flex flex-wrap gap-2'>
        {counties.map((county) => (
          <FigureEvidence key={county.id} label={`${county.name} budget observations`} labelKey='evidence.label.county_named' labelValues={{ name: county.name }}
            rows={county.figure_qualifications?.budget_lines} table='budget_lines' />
        ))}
      </div>
    </div>
  );
}
