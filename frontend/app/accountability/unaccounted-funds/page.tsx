'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useLang } from '@/lib/i18n/LangProvider';
import { AUDITS_MESSAGES } from '@/lib/i18n/messages/audits';
import { UNACCOUNTED_MESSAGES } from '@/lib/i18n/messages/unaccountedFunds';
import type { UnaccountedCase } from '@/types';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Search } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { reportCitationParts, reportPageHref } from './reportCitation';

interface UnaccountedResponse {
  total_cases: number;
  affected_counties: number;
  affected_national_entities: number;
  fiscal_years: string[];
  cases: UnaccountedCase[];
  withheld: { count: number; by_reason: Record<string, number> };
}

const PAGE_SIZE = 10;
const fieldClass = 'min-h-11 w-full appearance-none rounded border border-neutral-border bg-surface-elevated px-3 py-2 text-base text-neutral-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good';
const linkClass = 'rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good';

type Copy = (key: keyof typeof UNACCOUNTED_MESSAGES) => string;

function FindingCard({ finding, copy, qualifiedBasis }: {
  finding: UnaccountedCase;
  copy: Copy;
  qualifiedBasis: string;
}) {
  const { publisher, scope, volume } = reportCitationParts(finding.source);
  const report = [scope ? copy(scope) : null, finding.fiscal_year].filter(Boolean).join(' ');
  const citation = [
    publisher ?? copy('report'),
    report,
    volume && copy('volume').replace('{volume}', volume),
    finding.page_ref,
  ].filter(Boolean).join(' · ');
  const href = reportPageHref(finding);
  const entity = finding.entity || copy('entityUnknown');
  const heading = finding.heading?.toLowerCase() === 'basis for qualified opinion'
    ? qualifiedBasis : finding.heading;

  return (
    <article className='grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 py-3 lg:grid-cols-[minmax(0,1fr)_minmax(10rem,0.68fr)] lg:gap-x-6'>
      <h3 className='col-start-1 row-start-1 self-center break-words text-base font-semibold text-neutral-text'>
        {finding.entity_type === 'county' && finding.county_slug ? (
          <Link href={`/counties/${encodeURIComponent(finding.county_slug)}`}
            className={`inline-flex min-h-11 min-w-11 max-w-full items-center underline decoration-neutral-border underline-offset-4 hover:decoration-current ${linkClass}`}>
            <span className='min-w-0 break-words'>{entity}</span>
          </Link>
        ) : entity}
      </h3>
      <p className='col-start-2 row-start-1 max-w-36 self-center break-words text-right font-mono text-sm text-neutral-muted lg:row-start-2 lg:self-start lg:text-left'>
        {finding.fiscal_year}
      </p>
      <p data-reviewed-amount className='col-span-2 row-start-2 self-center text-sm font-semibold text-neutral-text lg:col-span-1 lg:col-start-2 lg:row-start-1'>
        {copy('reviewedAmount')}
      </p>
      <div className='col-span-2 row-start-3 min-w-0 lg:col-span-1 lg:col-start-1 lg:row-span-2 lg:row-start-2'>
        {heading && <p className='mb-1 break-words text-sm text-neutral-muted'>{heading}</p>}
        <blockquote lang='en' className='min-w-0 border-l-2 border-neutral-border pl-2.5'>
          <p className='break-words text-sm font-semibold text-neutral-text'>“{finding.title}”</p>
          {finding.excerpt && (
            <p className='mt-1 line-clamp-3 break-words text-sm leading-relaxed text-neutral-text'>
              {finding.excerpt}
            </p>
          )}
        </blockquote>
        {!finding.excerpt && <p className='mt-1 text-sm text-neutral-muted'>{copy('headingOnly')}</p>}
      </div>
      <div className='col-span-2 row-start-4 min-w-0 lg:col-span-1 lg:col-start-2 lg:row-start-3'>
        {href ? (
          <a href={href} target='_blank' rel='noopener noreferrer'
            className={`audit-receipt min-w-11 ${linkClass}`}>
            <span className='min-w-0 break-words'>{citation}</span>
            <ChevronRight size={15} aria-hidden='true' className='shrink-0' />
          </a>
        ) : <p className='break-words text-sm text-neutral-muted'>{citation}</p>}
      </div>
    </article>
  );
}

export default function UnaccountedFundsPage() {
  const { lang } = useLang();
  const copy: Copy = (key) => UNACCOUNTED_MESSAGES[key][lang];
  const [query, setQuery] = useState('');
  const [county, setCounty] = useState('');
  const [showAll, setShowAll] = useState(false);
  const { data, isLoading, isError, refetch } = useQuery<UnaccountedResponse>({
    queryKey: ['accountability', 'missing-funds'],
    queryFn: async ({ signal }) =>
      (await api.get<UnaccountedResponse>('/accountability/missing-funds', { signal })).data,
    staleTime: 10 * 60 * 1000,
  });

  const cases = data?.cases ?? [];
  const counties = Array.from(new Set(cases.flatMap((finding) => finding.county_name ? [finding.county_name] : [])))
    .sort((a, b) => a.localeCompare(b, 'en-KE'));
  const activeCounty = counties.includes(county) ? county : '';
  const term = query.trim().toLowerCase();
  const filtered = cases.filter((finding) => (
    (!activeCounty || finding.county_name === activeCounty)
    && (!term || [finding.entity, finding.county_name, finding.title, finding.excerpt, finding.fiscal_year]
      .some((value) => value?.toLowerCase().includes(term)))
  ));
  const visible = showAll ? filtered : filtered.slice(0, PAGE_SIZE);
  const settled = !isLoading && !isError && data;
  const format = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');

  const withheldLabels: Record<string, keyof typeof UNACCOUNTED_MESSAGES> = {
    source_document_has_no_url: 'sourceUnavailable',
    finding_text_unreadable_cid: 'unreadable',
    no_page_reference: 'unknownPage',
  };

  return (
    <PageShell title={copy('title')} back={{ href: '/audits', label: copy('back') }}>
      <div data-unaccounted-reader className='min-w-0 space-y-6'>
        <div className='space-y-3'>
          <p className='rounded border border-neutral-border bg-surface-base p-3 text-sm leading-relaxed text-neutral-text'>
            {copy('definition')}
          </p>
          <dl className='divide-y divide-neutral-border border-y border-neutral-border'>
            <div className='flex items-baseline justify-between gap-3 py-2'>
              <dt className='text-sm font-semibold text-neutral-text'>{copy('findings')}</dt>
              <dd className='font-display text-2xl font-semibold tabular-nums text-neutral-text'>{settled ? format.format(settled.total_cases) : '—'}</dd>
            </div>
            <div className='flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2 text-sm'>
              <dt className='font-semibold text-neutral-text'>{copy('amount')}</dt>
              <dd className='font-semibold text-neutral-text'>{copy('reviewedTotal')}</dd>
            </div>
          </dl>
          {settled && <>
            <p className='text-sm text-neutral-muted'>{copy('amountCoverage')}</p>
            {settled.fiscal_years.length > 0 && (
              <p className='text-sm text-neutral-muted'>
                {copy('periods').replace('{periods}', settled.fiscal_years.join(' · '))}
              </p>
            )}
            {settled.total_cases > 0 && (
              <p className='text-sm text-neutral-muted'>
                {copy('entityCoverage').replace('{counties}', format.format(settled.affected_counties))
                  .replace('{national}', format.format(settled.affected_national_entities))}
              </p>
            )}
          </>}
        </div>

        {isLoading && <p role='status' className='text-sm text-neutral-muted'>{copy('loading')}</p>}
        {isError && (
          <div role='alert' className='space-y-2 text-sm text-neutral-text'>
            <p>{copy('error')}</p>
            <button type='button' className={`audit-control min-w-11 ${linkClass}`} onClick={() => void refetch()}>{copy('retry')}</button>
          </div>
        )}

        {settled && settled.total_cases === 0 && (
          <section aria-labelledby='unaccounted-empty' className='space-y-2'>
            <h2 id='unaccounted-empty' className='font-display text-xl font-semibold text-neutral-text'>{copy('empty')}</h2>
            <p className='max-w-[68ch] text-sm leading-relaxed text-neutral-text'>{copy('emptyDetail')}</p>
          </section>
        )}

        {settled && settled.total_cases > 0 && (
          <div className='grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,17rem)]'>
            <section aria-labelledby='unaccounted-findings' className='min-w-0'>
              <h2 id='unaccounted-findings' className='border-b border-neutral-border pb-2 font-display text-xl font-semibold text-neutral-text'>
                {copy('list')}
              </h2>
              <div className='divide-y divide-neutral-border border-b border-neutral-border'>
                {visible.map((finding) => (
                  <FindingCard key={finding.finding_id} finding={finding} copy={copy}
                    qualifiedBasis={AUDITS_MESSAGES['audits.qualified_basis'][lang]} />
                ))}
                {visible.length === 0 && <p className='py-3 text-sm text-neutral-text'>{copy('noSearchResults')}</p>}
              </div>
            </section>

            <aside aria-labelledby='unaccounted-filters-heading'
              className='min-w-0 space-y-3 rounded border border-neutral-border bg-surface-base p-3 lg:sticky lg:top-24'>
              <h2 id='unaccounted-filters-heading' className='font-display text-xl font-semibold text-neutral-text'>{copy('filters')}</h2>
              <div>
                <label htmlFor='unaccounted-search' className='mb-1 block text-sm font-semibold text-neutral-text'>{copy('search')}</label>
                <div className='relative'>
                  <Search size={17} aria-hidden='true' className='pointer-events-none absolute left-3 top-3.5 text-neutral-muted' />
                  <input id='unaccounted-search' type='search' value={query}
                    onChange={(event) => { setQuery(event.target.value); setShowAll(false); }}
                    placeholder={copy('searchPlaceholder')} className={`${fieldClass} pl-9 placeholder:text-neutral-muted`} />
                </div>
              </div>
              <div>
                <label htmlFor='unaccounted-county' className='mb-1 block text-sm font-semibold text-neutral-text'>{copy('county')}</label>
                <div className='relative'>
                  <select id='unaccounted-county' value={activeCounty} className={`${fieldClass} pr-9`}
                    onChange={(event) => { setCounty(event.target.value); setShowAll(false); }}>
                    <option value=''>{copy('allCounties')}</option>
                    {counties.map((name) => <option key={name} value={name}>{name}</option>)}
                  </select>
                  <ChevronDown aria-hidden='true' size={16} className='pointer-events-none absolute right-3 top-3.5 text-neutral-muted' />
                </div>
              </div>
              <p role='status' className='text-sm text-neutral-muted'>
                {copy('visible').replace('{shown}', format.format(visible.length)).replace('{total}', format.format(filtered.length))}
              </p>
              {filtered.length > PAGE_SIZE && (
                <button type='button' className={`audit-control min-w-11 ${linkClass}`} onClick={() => setShowAll((current) => !current)}>
                  {showAll ? copy('showTen') : copy('showAll').replace('{total}', format.format(filtered.length))}
                </button>
              )}
            </aside>
          </div>
        )}

        {settled && settled.withheld.count > 0 && (
          <div className='text-sm text-neutral-muted'>
            <p>{copy('withheld').replace('{count}', format.format(settled.withheld.count))}</p>
            <ul role='list'>
              {Object.entries(settled.withheld.by_reason).filter(([, count]) => count > 0).map(([reason, count]) => (
                <li key={reason}>{format.format(count)} · {copy(withheldLabels[reason] ?? 'withheldOther')}</li>
              ))}
            </ul>
          </div>
        )}

        <section aria-labelledby='unaccounted-methodology' className='border-t border-neutral-border pt-3'>
          <h2 id='unaccounted-methodology' className='font-display text-xl font-semibold text-neutral-text'>{copy('methodology')}</h2>
          <p className='mt-1 max-w-[68ch] text-sm leading-relaxed text-neutral-text'>{copy('methodologyDetail')}</p>
          <Link href='/audits' className={`audit-receipt min-w-11 ${linkClass}`}>{copy('allAudits')}</Link>
        </section>
      </div>
    </PageShell>
  );
}
