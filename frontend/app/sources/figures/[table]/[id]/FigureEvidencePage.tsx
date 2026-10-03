'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import PageShell from '@/components/layout/PageShell';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import api from '@/lib/api/axios';
import { QUALIFICATION_TABLES, type Qualifications } from '@/lib/evidence/qualification';

interface VerificationResponse {
  value: string | null;
  reason: string | null;
  qualifications: Qualifications;
}

export default function FigureEvidencePage({ table, id }: { table: string; id: string }) {
  const valid = QUALIFICATION_TABLES.some(name => name === table) && /^[1-9]\d*$/.test(id);
  const query = useQuery({
    queryKey: ['figure-evidence', table, id],
    queryFn: async ({ signal }) => (await api.get<VerificationResponse>(`/provenance/verify/${table}`, { params: { record_id: id }, signal })).data,
    enabled: valid,
    staleTime: 0,
    retry: false,
  });
  return <PageShell title='Observation evidence' subtitle='Qualification for this exact stored observation and its individual measures.'>
    <div className='max-w-3xl space-y-4 rounded-xl border border-neutral-border bg-white dark:bg-surface-base p-5'>
      <Link href='/sources' className='inline-block min-h-11 py-2 underline'>All data sources</Link>
      {!valid ? <p role='alert'>This observation reference is invalid.</p> : query.isError ? <div>
        <p role='alert'>Could not load observation evidence. No verification result is available.</p>
        <button type='button' className='min-h-11 mt-2 rounded border border-neutral-border px-4 focus-visible:outline focus-visible:outline-2' disabled={query.isFetching} onClick={() => { void query.refetch({ cancelRefetch: false }); }}>Try again</button>
      </div> : query.isPending ? <p role='status'>Loading observation evidence…</p> : <>
        <p>Stored value: {query.data.value ?? 'Not published'}</p>
        {query.data.reason && <p>{query.data.reason.replace(/_/g, ' ')}</p>}
        <FigureEvidence label='this observation' qualifications={query.data.qualifications} />
        <button type='button' className='min-h-11 rounded border border-neutral-border px-4 focus-visible:outline focus-visible:outline-2' disabled={query.isFetching} onClick={() => { void query.refetch({ cancelRefetch: false }); }}>Refresh evidence</button>
      </>}
    </div>
  </PageShell>;
}
