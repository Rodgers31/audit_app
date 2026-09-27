/**
 * Unaccounted Funds
 *
 * Findings the Office of the Auditor-General's own report heads "Unaccounted
 * …" or "Loss of Funds", across county and national reports, each quoted in
 * the report's words and linked to its page (issue #233).
 *
 * It used to live at /accountability/missing-funds, which now redirects here
 * (next.config.js): "missing" is not the report's word. It shows no money
 * total — none of these findings carries an extracted amount, and where the
 * loader stores one it is the paragraph's only KES figure, which is often the
 * account balance under discussion rather than the sum unaccounted for.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import type { UnaccountedCase } from '@/types';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ExternalLink, Loader2, Search } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

interface UnaccountedResponse {
  basis: 'oag_finding_title';
  /** Always null — see the module comment. Never 0. */
  total_amount: null;
  total_amount_reason: 'no_amount_extracted';
  total_cases: number;
  affected_counties: number;
  affected_national_entities: number;
  fiscal_years: string[];
  cases: UnaccountedCase[];
  reason: 'no_matching_findings' | null;
  withheld: { count: number; by_reason: Record<string, number> };
}

export default function MissingFundsPage() {
  const [query, setQuery] = useState('');

  const { data, isLoading, error } = useQuery<UnaccountedResponse>({
    queryKey: ['accountability', 'missing-funds'],
    queryFn: async () =>
      (await api.get<UnaccountedResponse>('/accountability/missing-funds')).data,
    staleTime: 10 * 60 * 1000,
  });

  const filtered = useMemo(() => {
    const cases = data?.cases || [];
    const q = query.toLowerCase().trim();
    if (!q) return cases;
    return cases.filter(
      (c) =>
        c.entity.toLowerCase().includes(q) ||
        c.title.toLowerCase().includes(q) ||
        c.excerpt.toLowerCase().includes(q) ||
        (c.fiscal_year || '').toLowerCase().includes(q)
    );
  }, [data, query]);

  const settled = !isLoading && !error && !!data;
  const nothingListed = settled && data.total_cases === 0;

  return (
    <PageShell
      title='Unaccounted Funds'
      subtitle='Findings the Office of the Auditor-General’s own reports head as unaccounted for or a loss of funds, quoted in the report’s words and linked to the page.'
      back={{ href: '/', label: 'Home' }}>
      <div className='space-y-6'>
        {/* Top-line stats */}
        <div className='grid grid-cols-1 sm:grid-cols-3 gap-4'>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              Findings listed
            </div>
            <div className='text-3xl font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
              {settled ? data.total_cases : '—'}
            </div>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-1'>
              {settled && data.fiscal_years.length > 0
                ? `From the ${data.fiscal_years.join(' and ')} reports`
                : isLoading
                  ? 'Loading…'
                  : error
                    ? 'Could not load the list'
                    : ' '}
            </div>
          </div>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              Where
            </div>
            <div className='text-lg font-bold text-gray-900 dark:text-neutral-text tabular-nums leading-snug'>
              {settled && !nothingListed ? (
                <>
                  {data.affected_counties} {data.affected_counties === 1 ? 'county' : 'counties'}
                  <span className='text-gray-400 dark:text-neutral-muted/80 font-normal'> · </span>
                  {data.affected_national_entities} national{' '}
                  {data.affected_national_entities === 1 ? 'vote' : 'votes'}
                </>
              ) : (
                <span className='text-2xl font-semibold text-gray-400 dark:text-neutral-muted/80'>&mdash;</span>
              )}
            </div>
          </div>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              Amount involved
            </div>
            <div className='text-2xl font-semibold text-gray-400 dark:text-neutral-muted/80'>Not stated here</div>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-1'>
              The sum is not extracted from these findings. Open each page to read it.
            </div>
          </div>
        </div>

        {/* Nothing matches */}
        {nothingListed && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-200 dark:border-neutral-border p-8 text-center'>
            <AlertTriangle className='mx-auto text-gray-400 dark:text-neutral-muted/80 mb-3' size={24} />
            <h2 className='text-base font-semibold text-gray-900 dark:text-neutral-text mb-2'>
              No finding is listed here yet
            </h2>
            <p className='text-sm text-gray-600 dark:text-neutral-muted max-w-xl mx-auto leading-relaxed'>
              No extracted finding from a published report is headed “Unaccounted” or “Loss of
              Funds”. That is not a finding that public money is fully accounted for.
            </p>
          </div>
        )}

        {/* Search */}
        {settled && !nothingListed && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-4'>
            <div className='relative'>
              <Search
                size={14}
                className='absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-muted/80'
              />
              <input
                type='search'
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder='Search by county, ministry, heading or year…'
                aria-label='Search findings'
                className='w-full pl-9 pr-3 py-2 text-sm bg-transparent border border-gray-200 dark:border-neutral-border rounded-lg focus:outline-none focus:ring-2 focus:ring-gov-forest/30'
              />
            </div>
          </div>
        )}

        {isLoading && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 flex items-center justify-center gap-3 text-gray-500 dark:text-neutral-muted/80'>
            <Loader2 className='animate-spin' size={18} />
            <span>Loading findings…</span>
          </div>
        )}
        {error && (
          <div className='bg-rose-50 border border-rose-200 rounded-xl p-4 text-rose-800 text-sm'>
            Failed to load the findings. Please refresh.
          </div>
        )}

        {/* The findings */}
        {settled && !nothingListed && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border divide-y divide-gray-100 dark:divide-neutral-border'>
            {filtered.length === 0 ? (
              <div className='p-8 text-center text-sm text-gray-500 dark:text-neutral-muted/80'>
                No findings match your search.
              </div>
            ) : (
              filtered.map((c) => (
                <article key={c.finding_id} className='p-5'>
                  <div className='flex items-center gap-2 mb-1.5 flex-wrap text-xs'>
                    {c.entity_type === 'county' ? (
                      <Link
                        href={`/counties?search=${encodeURIComponent(c.entity.replace(/ County$/, ''))}`}
                        className='text-sm font-bold text-gray-900 dark:text-neutral-text hover:text-gov-forest hover:underline'>
                        {c.entity}
                      </Link>
                    ) : (
                      <span className='text-sm font-bold text-gray-900 dark:text-neutral-text'>{c.entity}</span>
                    )}
                    {c.fiscal_year && (
                      <span className='text-gray-500 dark:text-neutral-muted/80'>· {c.fiscal_year}</span>
                    )}
                    {c.heading && (
                      <span className='px-2 py-0.5 rounded-full border border-gray-200 dark:border-neutral-border text-gray-600 dark:text-neutral-muted'>
                        {c.heading}
                      </span>
                    )}
                  </div>
                  <h3 className='text-sm font-semibold text-gray-900 dark:text-neutral-text'>
                    “{c.title}”
                  </h3>
                  {c.excerpt ? (
                    <p className='mt-1 text-sm text-gray-700 dark:text-neutral-muted leading-relaxed line-clamp-3'>
                      {c.excerpt}
                    </p>
                  ) : (
                    <p className='mt-1 text-xs italic text-gray-500 dark:text-neutral-muted/80'>
                      Only the heading was extracted. Open the page to read the paragraph.
                    </p>
                  )}
                  {c.source.page_url && c.page_ref && (
                    <a
                      href={c.source.page_url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='mt-2 inline-flex items-center gap-1 text-xs text-gov-forest dark:text-emerald-100 hover:underline'>
                      <ExternalLink size={12} />
                      Source: report {c.page_ref}
                      {c.source.title ? ` — ${c.source.title}` : ''}
                    </a>
                  )}
                </article>
              ))
            )}
          </div>
        )}

        {settled && data.withheld.count > 0 && (
          <p className='text-xs text-gray-500 dark:text-neutral-muted/80'>
            {data.withheld.count} more matching finding{data.withheld.count === 1 ? ' is' : 's are'} held
            back because {data.withheld.count === 1 ? 'it does' : 'they do'} not trace to a page of a
            published report.
          </p>
        )}

        {/* Methodology */}
        <div className='bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40 rounded-xl p-5'>
          <div className='flex items-start gap-3'>
            <AlertTriangle className='text-amber-700 mt-0.5 shrink-0' size={18} />
            <div className='text-sm text-gray-700 dark:text-neutral-muted leading-relaxed'>
              <p className='font-semibold text-gray-900 dark:text-neutral-text mb-1'>What is listed here, and what is not</p>
              <p>
                A finding is listed only when the Auditor-General’s own heading for it begins
                “Unaccounted” or reads “Loss of Funds”, and it traces to a page of a published
                report. The match is on headings, so this is a minimum. A paragraph that mentions
                unaccounted money under another heading is not listed.
              </p>
              <p className='mt-2'>
                Findings about unsupported, irregular or unexplained expenditure are not listed.
                The report does not describe them as unaccounted for. They are all on the{' '}
                <Link href='/audits' className='underline hover:no-underline'>
                  audit findings
                </Link>{' '}
                page.
              </p>
              <p className='mt-2'>
                This page reports what an audit document says. It does not characterise any county,
                office or official beyond the wording of the cited report, and it does not describe
                the status of any investigation.
              </p>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
