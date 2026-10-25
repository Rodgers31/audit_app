'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useAdmin } from '@/lib/auth/admin';
import { generationApi } from '@/lib/api/socialGeneration';
import { describeGenerationReason } from '@/lib/socialGenerationReasons';
import { SocialErrorBanner } from './SocialNotice';
import styles from './social.module.css';

export default function GenerationPreview() {
  const { user } = useAuth(), { isAdmin } = useAdmin();
  const capabilities = useQuery({ queryKey: ['admin','social',user?.id,'generation','capabilities'], queryFn: ({signal}) => generationApi.capabilities(signal), enabled: isAdmin, retry: false, refetchOnWindowFocus: false });
  const [domain, setDomain] = useState('counties_budget'), [records, setRecords] = useState(''), [job, setJob] = useState('');
  const [reports, setReports] = useState(true), [backfill, setBackfill] = useState(false);
  const preview = useMutation({ mutationFn: generationApi.preview });
  const ids = records.split(',').map(v => Number(v.trim()));
  const valid = /^[1-9]\d*$/.test(job) && Number(job) <= 2147483647 && ids.length <= 25 && new Set(ids).size === ids.length && records.split(',').every(v => /^[1-9]\d*$/.test(v.trim())) && ids.every(v => Number.isSafeInteger(v) && v <= 2147483647);
  const selected = capabilities.data?.find(c => c.domain === domain);
  return <section className={styles.fields}><h2>Preview draft eligibility</h2>
    <p>Read-only preview saves no baseline, event, draft or backfill. Detection rechecks the current evidence. CoB county budgets support financial and neutral report drafts. National budget, KRA revenue releases and audits support neutral reports when their retained publisher date and scope qualify. Other sources show their missing contracts.</p>
    {capabilities.error && <SocialErrorBanner error={capabilities.error} onRetry={() => capabilities.refetch()} />}
    <form onSubmit={e => { e.preventDefault(); if (isAdmin && valid) preview.mutate({domain,record_ids:ids,ingestion_id:Number(job),reports,backfill}); }}>
      <fieldset disabled={!isAdmin || preview.isPending}><legend>Committed source selection</legend>
        <label>Source domain<select value={domain} onChange={e => { setDomain(e.target.value); preview.reset(); }}>{(capabilities.data ?? []).map(c => <option key={c.domain} value={c.domain}>{c.domain}</option>)}</select></label>
        {selected && <p>{describeGenerationReason(selected.reason)} {domain !== 'counties_budget' && selected.reports ? 'Use native report Extraction IDs from the completed job metadata.' : ''}</p>}
        <label>Preview record IDs (comma separated, up to 25)<input value={records} onChange={e => {setRecords(e.target.value);preview.reset();}} /></label>
        <label>Preview ingestion job ID<input inputMode='numeric' value={job} onChange={e => {setJob(e.target.value);preview.reset();}} /></label>
        <label><input type='checkbox' checked={reports} onChange={e => {setReports(e.target.checked);preview.reset();}} /> Preview neutral report evidence</label>
        <label><input type='checkbox' checked={backfill} onChange={e => {setBackfill(e.target.checked);preview.reset();}} /> Preview explicit first-observation backfill</label>
        <button type='submit' className={styles.button} disabled={!valid || !selected || preview.isPending}>Preview without saving</button>
      </fieldset>
    </form>
    {preview.error && <SocialErrorBanner error={preview.error} />}
    <div aria-live='polite'>{preview.data && <><p>Runtime drafts: {preview.data.drafts_enabled ? 'enabled for this source' : 'off or unsupported'}. Preview does not enable any control.</p><Link href={`/admin/ingestion/${Number(job)}`}>Inspect ingestion job {Number(job)}</Link>{preview.data.results.map(r => <article key={r.record_id}><h3>Record {r.record_id} · {r.status.replaceAll('_',' ')}</h3><p>{describeGenerationReason(r.reason)}</p>{r.source_document_id && <p>Verified source document #{r.source_document_id}</p>}</article>)}</>}</div>
  </section>;
}
