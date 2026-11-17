'use client';

import { useQuery } from '@tanstack/react-query';
import PageShell from '@/components/layout/PageShell';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import api from '@/lib/api/axios';
import { useLang } from '@/lib/i18n/LangProvider';
import { QUALIFICATION_TABLES } from '@/lib/evidence/qualification';
import { figureReceipt, type VerificationResponse } from './figureReceipt';
import { figureReceiptCopy } from './messages';

export default function FigureEvidencePage({ table, id }: { table: string; id: string }) {
  const { t, lang } = useLang();
  const copy = figureReceiptCopy[lang];
  const tableName = QUALIFICATION_TABLES.find(name => name === table);
  const valid = !!tableName && /^[1-9]\d*$/.test(id);
  const query = useQuery({
    queryKey: ['figure-evidence', table, id],
    queryFn: async ({ signal }) => (await api.get<VerificationResponse>(`/provenance/verify/${table}`, { params: { record_id: id }, signal })).data,
    enabled: valid,
    staleTime: 0,
    retry: false,
  });
  const report = valid && !query.isError ? query.data : undefined;
  const receipt = tableName && report ? figureReceipt(tableName, report, lang) : undefined;
  const title = receipt?.title ?? copy.title;

  return (
    <PageShell title={title} back={{ href: '/sources', label: t('evidence.page.all_sources') }} breadcrumbs={false}>
      <title>{`${title} | AuditGava`}</title>
      <div className='max-w-3xl space-y-4 text-sm text-neutral-text'>
        {!valid ? (
          <p role='alert'>{t('evidence.page.invalid')}</p>
        ) : query.isError ? (
          <div>
            <p role='alert'>{t('evidence.page.error')}</p>
            <button type='button' className='audit-control mt-2' disabled={query.isFetching} onClick={() => { void query.refetch({ cancelRefetch: false }); }}>
              {t('evidence.page.retry')}
            </button>
          </div>
        ) : receipt && report ? (
          <>
            {!receipt.hasValue && <p className='text-neutral-muted'>{t('evidence.page.not_published')}</p>}
            <dl aria-label={copy.receipt} className='divide-y divide-neutral-border border-y border-neutral-border'>
              <div className='grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] items-center gap-3 py-2'>
                <dt className='text-neutral-muted'>{copy.publishedIn}</dt>
                <dd className='min-w-0 break-words font-semibold'>
                  {receipt.sourceUrl ? (
                    <a href={receipt.sourceUrl} className='audit-receipt break-words'>
                      <span className='min-w-0'>{receipt.source}</span>
                      <span aria-hidden='true'>›</span>
                    </a>
                  ) : receipt.source}
                </dd>
              </div>
              <div className='grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-3 py-2'>
                <dt className='text-neutral-muted'>{copy.describes}</dt>
                <dd className='min-w-0 break-words font-semibold'>{receipt.period}</dd>
              </div>
              <div className='grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-3 py-2'>
                <dt className='text-neutral-muted'>{copy.sourceRetrieved}</dt>
                <dd className='min-w-0 break-words font-semibold'>{receipt.retrieved}</dd>
              </div>
            </dl>
            {report.reason && <p className='break-words text-neutral-muted'>{report.reason.replace(/_/g, ' ')}</p>}
            <FigureEvidence label='this observation' labelKey='evidence.label.this_observation' qualifications={report.qualifications} />
          </>
        ) : (
          <p role='status'>{t('evidence.page.loading')}</p>
        )}
      </div>
    </PageShell>
  );
}
