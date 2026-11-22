'use client';

import FigureEvidence from '@/components/evidence/FigureEvidence';
import type { NationalLoan, NationalLoansResponse } from '@/lib/api/debt';
import { displayLenderName } from '@/lib/debt/lenderName';
import { annualCostCell, sortLoans, type LoanSortKey } from '@/lib/debt/loanInterest';
import { evidenceUrl, qualificationMessageKey } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { readLenderQuery } from '@/lib/search/publishedSearch';
import { fmtKES } from '@/lib/utils';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useMemo, useRef, useState } from 'react';

const INITIAL_ROWS = 10;
const GROUPS = ['all', 'domestic', 'multilateral', 'bilateral', 'commercial'] as const;
type Group = (typeof GROUPS)[number];
type Translate = (key: TranslationKey) => string;

const CATEGORY = new Map<string, { group?: Group; label: TranslationKey }>([
  ['domestic_bonds', { group: 'domestic', label: 'debt.lenders.domestic_bonds' }],
  ['domestic_bills', { group: 'domestic', label: 'debt.lenders.domestic_bills' }],
  ['domestic_overdraft', { group: 'domestic', label: 'debt.lenders.domestic_overdraft' }],
  ['external_multilateral', { group: 'multilateral', label: 'debt.register.group.multilateral' }],
  ['external_bilateral', { group: 'bilateral', label: 'debt.register.group.bilateral' }],
  ['external_commercial', { group: 'commercial', label: 'debt.register.group.commercial' }],
  ['county_guaranteed', { label: 'debt.lenders.county_guaranteed' }],
]);

function publishedRate(loan: NationalLoan) {
  const basis = loan.interest_rate_basis;
  const rate = loan.interest_rate_pct;
  const source = evidenceUrl(loan.interest_rate_source?.url);
  if (!source || rate == null || !Number.isFinite(rate) || rate < 0) return null;
  if (basis !== 'coupon_weighted_average' && basis !== 'auction_yield') return null;
  return { rate, basis, source };
}

function Rate({ loan, t }: { loan: NationalLoan; t: Translate }) {
  const rate = publishedRate(loan);
  if (!rate) return <span className='text-neutral-muted'>{t('debt.register.not_published')}</span>;
  const conflicting = qualificationMessageKey(loan.qualifications?.interest_rate) === 'evidence.status.conflicting';
  return (
    <div className='min-w-0'>
      <span className='tabular-nums'>{rate.rate.toFixed(2)}%</span>
      <a href={rate.source} target='_blank' rel='noopener noreferrer'
        className='audit-receipt w-full justify-start text-left [overflow-wrap:anywhere]'>
        {t(rate.basis === 'auction_yield' ? 'debt.register.rate_yield' : 'debt.register.rate_coupon')}
      </a>
      {conflicting && <span className='block text-neutral-muted'>{t('debt.register.rate_conflict')}</span>}
    </div>
  );
}

function AnnualInterest({ loan, t }: { loan: NationalLoan; t: Translate }) {
  const cell = annualCostCell(loan);
  if (cell.value == null || !Number.isFinite(cell.value)) {
    return <span className='text-neutral-muted'>{t('debt.register.not_published')}</span>;
  }
  const year = cell.tag?.split(' ')[1];
  const tag = cell.tag === 'modelled'
    ? t('debt.register.modelled')
    : year ? t('debt.register.paid_in').replace('{year}', year) : t('debt.register.paid');
  return (
    <>
      <span className='tabular-nums' title={cell.title || undefined}>{fmtKES(cell.value)}</span>
      <span className='block text-neutral-muted'>{tag}</span>
    </>
  );
}

function Lender({ loan, name, category, t }: { loan: NationalLoan; name: string; category?: string; t: Translate }) {
  const asOf = loan.interest_rate_source?.as_of;
  const rateNote = publishedRate(loan) ? [
    loan.interest_rate_label,
    asOf ? t('debt.register.rate_as_of').replace('{date}', () => asOf) : null,
  ].filter(Boolean).join(' ') : undefined;

  return (
    <>
      <p className='min-w-0 max-w-[36ch] font-semibold [overflow-wrap:anywhere]'>{name}</p>
      {category && <p className='text-neutral-muted'>{category}</p>}
      <div onClickCapture={event => {
        // WebKit does not focus pointer-activated buttons by default. Focus the
        // receipt before the native dialog records where to restore focus.
        if (event.target instanceof Element) {
          event.target.closest<HTMLButtonElement>('button[aria-haspopup="dialog"]')?.focus({ preventScroll: true });
        }
      }}>
        <FigureEvidence label={name} qualifications={loan.qualifications} table='loans'
          recordId={loan.record_id ?? loan.id} explanation={rateNote} />
      </div>
    </>
  );
}

interface LoanRegisterProps {
  data: NationalLoansResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  retry: () => void;
}

function LenderSearchPrefill({ setQuery }: { setQuery: (value: string) => void }) {
  const params = useSearchParams();
  const lender = readLenderQuery(params?.getAll('lender') ?? []);
  useEffect(() => setQuery(lender), [lender, setQuery]);
  return null;
}

export default function LoanRegister({ data, isLoading, isError, isFetching, retry }: LoanRegisterProps) {
  const { t, lang } = useLang();
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState<Group>('all');
  const [sort, setSort] = useState<LoanSortKey>('outstanding');
  const [showAll, setShowAll] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const rows = useMemo(() => {
    // Keep the register's existing descending sorts. Rate sort uses the same
    // published references as the Rate cell, with missing values at the end.
    const loans = (data?.loans ?? []).map(loan =>
      loan.interest_rate_pct != null && !publishedRate(loan) ? { ...loan, interest_rate_pct: null } : loan);
    const search = displayLenderName(query).toLocaleLowerCase(lang === 'sw' ? 'sw-KE' : 'en-KE');
    return sortLoans(loans, sort)
      .map(loan => ({ loan, name: displayLenderName(loan.lender), category: CATEGORY.get(loan.lender_type) }))
      .filter(({ name, category }) => (group === 'all' || category?.group === group) &&
        name.toLocaleLowerCase(lang === 'sw' ? 'sw-KE' : 'en-KE').includes(search));
  }, [data, group, lang, query, sort]);
  const visible = showAll ? rows : rows.slice(0, INITIAL_ROWS);
  const count = (n: number) => n.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const selectSort = (value: string) => setSort(value === 'rate' || value === 'service' ? value : 'outstanding');

  return (
    <section id='loan-register' aria-labelledby='loan-register-heading' className='min-w-0 scroll-mt-24 space-y-3' data-loan-register>
      <Suspense fallback={null}><LenderSearchPrefill setQuery={setQuery} /></Suspense>
      <h2 id='loan-register-heading' className='font-display text-2xl text-neutral-text sm:text-3xl'>
        {t('debt.register.title')}
      </h2>
      <p className='max-w-prose text-sm leading-relaxed text-neutral-muted'>{t('debt.register.scope')}</p>
      {isLoading && <p role='status' className='text-sm text-neutral-muted'>{t('debt.register.loading')}</p>}
      {isError && (
        <div className='space-y-2'>
          <p role='alert' className='text-sm text-neutral-text'>
            {t(data ? 'debt.register.refresh_error' : 'debt.register.error')}
          </p>
          <button type='button' onClick={retry} disabled={isFetching} className='audit-control'>
            {t(isFetching ? 'debt.register.loading' : 'debt.maturity.retry')}
          </button>
        </div>
      )}
      {data && (data.loans.length === 0 ? (
        <p className='text-sm text-neutral-muted'>{t('debt.register.empty')}</p>
      ) : (
        <>
          <div className='flex min-w-0 flex-wrap gap-3'>
            <label className='flex min-w-0 basis-full flex-col gap-1 text-sm font-medium text-neutral-text sm:basis-64'>
              {t('debt.register.search')}
              <input ref={searchInput} type='search' value={query} onChange={event => setQuery(event.target.value)}
                className='min-h-11 min-w-0 rounded border border-neutral-muted bg-surface-base px-3 text-sm text-neutral-text' />
            </label>
            <label className='flex min-w-0 max-w-full flex-col gap-1 text-sm font-medium text-neutral-text'>
              {t('debt.register.sort')}
              <select value={sort} onChange={event => selectSort(event.target.value)}
                className='min-h-11 min-w-0 max-w-full rounded border border-neutral-muted bg-surface-base px-3 text-sm text-neutral-text'>
                <option value='outstanding'>{t('debt.register.sort_balance')}</option>
                <option value='rate'>{t('debt.register.sort_rate')}</option>
                <option value='service'>{t('debt.register.sort_interest')}</option>
              </select>
            </label>
          </div>
          <fieldset className='flex min-w-0 flex-wrap gap-2'>
            <legend className='sr-only'>{t('debt.register.filter')}</legend>
            {GROUPS.map(option => (
              <button key={option} type='button' aria-pressed={group === option} onClick={() => setGroup(option)}
                className='audit-control min-w-11 rounded-full aria-pressed:border-neutral-text aria-pressed:bg-surface-sunken aria-pressed:ring-1 aria-pressed:ring-inset aria-pressed:ring-neutral-text'>
                {t(`debt.register.group.${option}`)}
              </button>
            ))}
          </fieldset>
          <div className='flex flex-wrap items-center gap-x-4 gap-y-2'>
            <p role='status' className='min-w-0 text-sm text-neutral-muted'>
              {t('debt.register.count').replace('{shown}', count(visible.length)).replace('{total}', count(rows.length))}
            </p>
            {rows.length > INITIAL_ROWS && (
              <button type='button' onClick={() => setShowAll(value => !value)} aria-expanded={showAll} aria-controls='loan-register-rows'
                className='audit-control'>
                {showAll ? t('debt.register.show_top') : t('debt.register.show_all').replace('{count}', count(rows.length))}
              </button>
            )}
          </div>
          {rows.length === 0 ? (
            <div className='space-y-2'>
              <p className='text-sm text-neutral-muted'>{t('debt.register.no_matches')}</p>
              <button type='button' className='audit-control' onClick={() => {
                setGroup('all');
                setQuery('');
                searchInput.current?.focus();
              }}>
                {t('debt.register.reset')}
              </button>
            </div>
          ) : (
            <div id='loan-register-rows' className='audit-panel [overflow-wrap:anywhere]'>
              <table aria-label={t('debt.register.title')} className='hidden w-full table-fixed text-sm text-neutral-text md:table'>
                <thead className='border-b border-neutral-border bg-surface-sunken text-left'>
                  <tr>
                    <th scope='col' className='w-[27%] px-3 py-2'>{t('debt.register.lender')}</th>
                    <th scope='col' className='w-[14%] px-2 py-2'>{t('debt.register.category')}</th>
                    <th scope='col' aria-sort={sort === 'outstanding' ? 'descending' : undefined} className='w-[14%] px-2 py-2'>{t('debt.register.balance')}</th>
                    <th scope='col' aria-sort={sort === 'rate' ? 'descending' : undefined} className='w-[18%] px-2 py-2'>{t('debt.register.rate')}</th>
                    <th scope='col' aria-sort={sort === 'service' ? 'descending' : undefined} className='w-[14%] px-2 py-2'>{t('debt.register.annual_interest')}</th>
                    <th scope='col' className='w-[13%] px-2 py-2'>{t('debt.register.maturity')}</th>
                  </tr>
                </thead>
                <tbody className='divide-y divide-neutral-border align-top'>
                  {visible.map(({ loan, name, category }) => (
                    <tr key={loan.record_id ?? loan.id ?? loan.lender}>
                      <td className='px-3 py-2'><Lender loan={loan} t={t} name={name || t('debt.lenders.name_missing')} /></td>
                      <td className='px-2 py-2 text-neutral-muted'>{t(category?.label ?? 'debt.register.other')}</td>
                      <td className='px-2 py-2 font-semibold tabular-nums'>
                        {Number.isFinite(loan.outstanding_numeric) ? fmtKES(loan.outstanding_numeric) : t('debt.lenders.amount_missing')}
                      </td>
                      <td className='px-2 py-2'><Rate loan={loan} t={t} /></td>
                      <td className='px-2 py-2'><AnnualInterest loan={loan} t={t} /></td>
                      <td className='px-2 py-2'>{loan.maturity_date || t('debt.register.maturity_unavailable')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul role='list' aria-label={t('debt.register.title')} className='divide-y divide-neutral-border text-sm text-neutral-text md:hidden'>
                {visible.map(({ loan, name, category }) => (
                  <li key={loan.record_id ?? loan.id ?? loan.lender} className='min-w-0 space-y-2 p-4'>
                    <Lender loan={loan} t={t} name={name || t('debt.lenders.name_missing')}
                      category={t(category?.label ?? 'debt.register.other')} />
                    <dl className='grid grid-cols-2 gap-3'>
                      <div className='min-w-0'>
                        <dt className='text-neutral-muted'>{t('debt.register.balance')}</dt>
                        <dd className='font-semibold tabular-nums'>
                          {Number.isFinite(loan.outstanding_numeric) ? fmtKES(loan.outstanding_numeric) : t('debt.lenders.amount_missing')}
                        </dd>
                      </div>
                      <div className='min-w-0'>
                        <dt className='text-neutral-muted'>{t('debt.register.rate')}</dt>
                        <dd><Rate loan={loan} t={t} /></dd>
                      </div>
                      <div className='min-w-0'>
                        <dt className='text-neutral-muted'>{t('debt.register.annual_interest')}</dt>
                        <dd><AnnualInterest loan={loan} t={t} /></dd>
                      </div>
                      <div className='min-w-0'>
                        <dt className='text-neutral-muted'>{t('debt.register.maturity')}</dt>
                        <dd>{loan.maturity_date || t('debt.register.maturity_unavailable')}</dd>
                      </div>
                    </dl>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className='max-w-prose text-sm leading-relaxed text-neutral-muted'>{t('debt.register.interest_scope')}</p>
        </>
      ))}
    </section>
  );
}
