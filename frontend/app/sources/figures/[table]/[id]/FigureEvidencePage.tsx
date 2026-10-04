'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import PageShell from '@/components/layout/PageShell';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import api from '@/lib/api/axios';
import { useLang } from '@/lib/i18n/LangProvider';
import { QUALIFICATION_TABLES, type Qualifications } from '@/lib/evidence/qualification';

interface VerificationResponse {
  value: string | null;
  reason: string | null;
  qualifications: Qualifications;
}

export default function FigureEvidencePage({ table, id }: { table: string; id: string }) {
  const { t } = useLang();
  const valid = QUALIFICATION_TABLES.some(name => name === table) && /^[1-9]\d*$/.test(id);
  const query = useQuery({
    queryKey: ['figure-evidence', table, id],
    queryFn: async ({ signal }) => (await api.get<VerificationResponse>(`/provenance/verify/${table}`, { params: { record_id: id }, signal })).data,
    enabled: valid,
    staleTime: 0,
    retry: false,
  });
  return <PageShell title={t('evidence.page.title')} subtitle={t('evidence.page.subtitle')}>
    <div className='max-w-3xl space-y-4 rounded-xl border border-neutral-border bg-white dark:bg-surface-base p-5'>
      <Link href='/sources' className='inline-block min-h-11 py-2 underline'>{t('evidence.page.all_sources')}</Link>
      {!valid ? <p role='alert'>{t('evidence.page.invalid')}</p> : query.isError ? <div>
        <p role='alert'>{t('evidence.page.error')}</p>
        <button type='button' className='min-h-11 mt-2 rounded border border-neutral-border px-4 focus-visible:outline focus-visible:outline-2' disabled={query.isFetching} onClick={() => { void query.refetch({ cancelRefetch: false }); }}>{t('evidence.page.retry')}</button>
      </div> : query.isPending ? <p role='status'>{t('evidence.page.loading')}</p> : <>
        <p>{t('evidence.page.stored_value')}: {query.data.value ?? t('evidence.page.not_published')}</p>
        {query.data.reason && <p>{query.data.reason.replace(/_/g, ' ')}</p>}
        <FigureEvidence label={t('evidence.page.this_observation')} qualifications={query.data.qualifications} />
        <button type='button' className='min-h-11 rounded border border-neutral-border px-4 focus-visible:outline focus-visible:outline-2' disabled={query.isFetching} onClick={() => { void query.refetch({ cancelRefetch: false }); }}>{t('evidence.page.refresh')}</button>
      </>}
    </div>
  </PageShell>;
}
