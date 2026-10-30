'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import PageShell from '@/components/layout/PageShell';
import { getPublicReport, reportSelector } from '@/lib/api/publicReports';
import { useLang } from '@/lib/i18n/LangProvider';

export function ReportViewFallback() {
  const { t } = useLang();
  return <PageShell title={t('report.title')} subtitle={t('report.subtitle')}><p role='status'>{t('report.loading')}</p></PageShell>;
}

export default function ReportView({ domain, documentId }: { domain: string; documentId: string }) {
  const queryParams = useSearchParams();
  const { t, lang } = useLang();
  const selector = reportSelector(domain, documentId, new URLSearchParams(queryParams.toString()));
  const query = useQuery({ queryKey: ['public-report', selector], queryFn: ({ signal }) => getPublicReport(selector!, signal), enabled: !!selector, staleTime: 0, retry: false });
  const data = selector && !query.isError ? query.data : undefined;
  const formatDate = (value: string) => new Intl.DateTimeFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(value+'T12:00:00Z'));
  return <PageShell title={data ? `${data.entity} · ${data.title}` : t('report.title')} subtitle={data ? `${data.period} · ${data.publisher}` : t('report.subtitle')}>
    <div className='mx-auto max-w-4xl space-y-7'>
      <Link href='/sources' className='inline-flex min-h-11 items-center text-gov-forest underline underline-offset-4 dark:text-emerald-300'>{t('evidence.page.all_sources')}</Link>
      {!selector || query.isError ? <section role='alert' className='rounded-2xl border border-neutral-border bg-white p-6 dark:bg-surface-base'>
        <h2 className='text-xl font-semibold'>{t('report.unavailable')}</h2>
        <p className='mt-2 max-w-prose'>{t('report.no_substitution')}</p>
        {selector && <button type='button' className='mt-4 min-h-11 rounded-lg border border-neutral-border px-4 py-2 focus-visible:outline focus-visible:outline-2' disabled={query.isFetching} onClick={() => void query.refetch()}>{t('evidence.page.retry')}</button>}
      </section> : !data ? <p role='status'>{t('report.loading')}</p> : <>
        <section aria-label={t('report.scope')} className='rounded-2xl border border-neutral-border bg-white p-6 dark:bg-surface-base sm:p-8'>
          <p className='text-sm font-semibold uppercase tracking-wide text-gov-forest dark:text-emerald-300'>{data.availability === 'catalogued' ? t('report.catalogued') : t('report.reporting_period')}</p>
          <h2 className='mt-2 text-2xl font-semibold'>{data.period}</h2>
          {data.period_start && data.period_end && <p className='mt-2'>{formatDate(data.period_start)} – {formatDate(data.period_end)}</p>}
          <p className='mt-4'>{data.published_on ? `${t('report.published')} ${formatDate(data.published_on)}` : `${t('report.catalogue_date')} ${formatDate(data.catalogued_on!)}. ${t('report.publication_unknown')}`}</p>
          {data.view === 'report' && <p className='mt-4 max-w-prose text-sm'>{t('report.full_record')}</p>}
        </section>
        {!!data.figures.length && <section aria-label={t('report.figures')}>
          <h2 className='mb-4 text-xl font-semibold'>{t('report.figures')}</h2>
          <div className='grid gap-4 sm:grid-cols-2'>{data.figures.map((figure, index) => <article key={`${figure.metric}-${index}`} className='min-w-0 rounded-2xl border border-neutral-border bg-white p-6 dark:bg-surface-base'>
            <p className='text-sm'>{figure.metric}</p>
            <p className='my-3 break-words text-3xl font-semibold tracking-tight text-gov-forest dark:text-emerald-300'>{figure.display_value}</p>
            <p className='text-sm'>{figure.classification === 'actual' ? t('report.reported') : figure.classification === 'modelled' ? t('report.modelled') : t('report.projected')}</p>
            <details className='mt-5 border-t border-neutral-border pt-2 text-sm'><summary className='min-h-11 cursor-pointer py-3 focus-visible:outline focus-visible:outline-2'>{t('report.figure_details')}</summary>
              <dl className='space-y-3 pb-2'><div><dt className='font-medium'>{t('report.exact_value')}</dt><dd className='break-words'>{figure.value} {figure.scale} {figure.unit}</dd></div>
                <div><dt className='font-medium'>{t('report.basis')}</dt><dd>{figure.comparison_basis}</dd></div><div><dt className='font-medium'>{t('evidence.locator')}</dt><dd>{figure.locator}</dd></div></dl>
            </details>
          </article>)}</div>
          {data.domain === 'pending_bills' && <p className='mt-4 max-w-prose text-sm'>{t('report.pending_limit')}</p>}
        </section>}
        <section aria-label={t('report.sources')} className='rounded-2xl border border-neutral-border bg-white p-6 dark:bg-surface-base sm:p-8'>
          <h2 className='text-xl font-semibold'>{t('report.sources')}</h2><p className='mt-2 max-w-prose text-sm'>{t('report.source_help')}</p>
          <ul className='mt-5 divide-y divide-neutral-border'>{data.sources.map((source, index) => <li key={`${source.url}-${index}`} className='py-4 first:pt-0 last:pb-0'>
            <p className='font-medium'>{source.publisher}</p><p className='mt-1 max-w-prose break-words text-sm'>{source.locator}</p>
            <a href={source.url} target='_blank' rel='noopener noreferrer' className='mt-2 inline-flex min-h-11 items-center break-all text-gov-forest underline underline-offset-4 dark:text-emerald-300'>{data.availability === 'catalogued' ? t('report.open_entry') : t('report.open_source')} ↗</a>
          </li>)}</ul>
        </section>
      </>}
    </div>
  </PageShell>;
}
