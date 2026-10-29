/**
 * /admin/ingestion/[jobId] — single-job detail view.
 *
 * Shows recorded timing and counters with safe operational diagnostics.
 */
'use client';

import GenerationOutcomes from '@/components/admin/social/GenerationOutcomes';
import ReceiptRetention from '@/components/admin/ReceiptRetention';
import PageShell from '@/components/admin/AdminPageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import styles from '@/components/admin/admin.module.css';
import { sourceLabel } from '@/lib/admin/sourceLabels';
import Link from 'next/link';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  XCircle,
} from 'lucide-react';
import { use, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import {activeJob, ingestionFilters, formatIngestionTime as formatDate, parseIngestionJob, type IngestionJob} from '@/lib/admin/ingestion';
import {useOperationsAccess} from '@/lib/admin/ingestionPolling';

export default function IngestionJobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  return <Suspense fallback={<PageShell title='Data update'><p role='status'>Loading job…</p></PageShell>}><IngestionJobDetail jobId={jobId}/></Suspense>;
}

function IngestionJobDetail({jobId}:{jobId:string}) {
  const search=useSearchParams();
  const listQuery=ingestionFilters(new URLSearchParams(search)).canonical.toString();
  const backHref='/admin/ingestion'+(listQuery?'?'+listQuery:'');
  const access = useOperationsAccess(['ingestion-job']);
  const validId = /^\d+$/.test(jobId) && Number(jobId) >= 1 && Number(jobId) <= 2147483647;
  const job = useQuery<IngestionJob>({
    queryKey: ['admin', 'ingestion-job', access.actorId, jobId],
    queryFn: async ({ signal }) => {
      const data = parseIngestionJob((await api.get(`/admin/ingestion-jobs/${Number(jobId)}`, { signal })).data);
      if(data.id !== Number(jobId)) throw new Error('Mismatched job');
      return data;
    },
    enabled: access.enabled && validId,
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: query => access.enabled && !query.state.error && query.state.data && activeJob(query.state.data) ? 15_000 : false,
    staleTime: 15_000,
  });

  const {isLoading,error,refetch,isFetching} = job;
  const data = access.isAdmin && !error ? job.data : undefined;
  if (!access.isAdmin) return <PageShell title='Ingestion job'><p>{access.isLoading ? 'Verifying access…' : 'Admin access required.'}</p></PageShell>;
  if (!validId) return <PageShell title='Invalid job ID' back={{href:backHref,label:'Back to ingestion jobs'}}><p>Choose a job from the ingestion list.</p></PageShell>;

  if (isLoading || (!data && !error)) {
    return (
      <PageShell
        title={`Job #${jobId}`}
        back={{ href: backHref, label: 'Back to ingestion jobs' }}>
        <div className='py-16 flex justify-center'>
          <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
        </div>
      </PageShell>
    );
  }

  if (error || !data) {
    return (
      <PageShell
        title={`Job #${jobId}`}
        back={{ href: backHref, label: 'Back to ingestion jobs' }}>
        <div className='py-16 flex flex-col items-center gap-3'>
          <XCircle className='w-10 h-10 text-gov-copper dark:text-red-400' />
          <p className='text-gov-copper dark:text-red-400 text-sm'>{(error as {response?:{status?:number}})?.response?.status === 404 ? 'Job not found.' : 'Could not load job.'}</p>
          <button onClick={() => { if(access.enabled) void refetch(); }} disabled={isFetching || !access.enabled} className='text-sm underline'>Retry</button>
        </div>
      </PageShell>
    );
  }

  return <PageShell title={sourceLabel(data.domain)} subtitle={`Data update · job #${data.id}`} back={{href:backHref,label:'Back to data updates'}}>
    <div className={styles.workspace}>
      <section className={styles.panel} aria-labelledby='data-outcome-heading'><div className={styles.sectionHeading}><div><h2 id='data-outcome-heading'>Data outcome</h2><p>Recorded job status. Worker activity and financial freshness require their own evidence.</p></div><button className={styles.button} disabled={isFetching||!access.enabled} onClick={()=>{if(access.enabled)void refetch();}}>Refresh outcome</button></div>
        <StatusBadge status={data.status} hasErrors={data.error_count>0}/>{data.dry_run&&<p className={styles.quiet}>Dry run · no publication was permitted by this job.</p>}
        <dl className={`${styles.facts} mt-6`}><div><dt>Data items processed</dt><dd>{data.items_processed.toLocaleString()}</dd></div><div><dt>Data items created</dt><dd>{data.items_created.toLocaleString()}</dd></div><div><dt>Data items updated</dt><dd>{data.items_updated.toLocaleString()}</dd></div><div><dt>Recorded errors</dt><dd>{data.error_count.toLocaleString()}</dd></div></dl>
        <p className={styles.quiet}>Finished {formatDate(data.finished_at)} · {formatDuration(data.duration_seconds)}</p>
      </section>
      <GenerationOutcomes metadata={data.metadata} domain={data.domain} jobId={data.id}/>
      {data.error_count>0&&<div className={styles.notice}><strong>Inspect the recorded failure before retrying</strong><p>Diagnostic details are withheld from this page. Use the dedicated runner logs and the original command receipt to determine whether work committed.</p><Link className={styles.button} href='/admin/etl'>Run & recover</Link></div>}
      <ReceiptRetention metadata={data.metadata}/>
      <details className={styles.disclosure}><summary>Timing and safe technical details</summary><div><dl className={styles.facts}><div><dt>Started</dt><dd>{data.status==='pending'?'Awaiting execution':formatDate(data.started_at)}</dd></div><div><dt>Created</dt><dd>{formatDate(data.created_at)}</dd></div><div><dt>Stored source domain</dt><dd>{data.domain}</dd></div></dl><pre className={styles.raw}>{JSON.stringify(data.metadata,null,2)}</pre></div></details>
    </div>
  </PageShell>;
}

/* ── Helpers ── */

function StatusBadge({ status, hasErrors }: { status: string; hasErrors: boolean }) {
  const config = ((): {
    bg: string;
    text: string;
    icon: React.ElementType;
    label: string;
  } => {
    switch (status) {
      case 'completed':
        return hasErrors
          ? {
              bg: 'bg-gov-warning/15',
              text: 'text-gov-warning dark:text-amber-300',
              icon: AlertTriangle,
              label: 'completed w/ errors',
            }
          : {
              bg: 'bg-emerald-100 dark:bg-emerald-900/40',
              text: 'text-emerald-700 dark:text-emerald-300',
              icon: CheckCircle2,
              label: status,
            };
      case 'completed_with_errors':
        return {
          bg: 'bg-gov-warning/15',
          text: 'text-gov-warning dark:text-amber-300',
          icon: AlertTriangle,
          label: 'completed w/ errors',
        };
      case 'failed':
        return { bg: 'bg-gov-copper/15', text: 'text-gov-copper dark:text-red-400', icon: XCircle, label: status };
      case 'running':
        return { bg: 'bg-blue-100 dark:bg-blue-900/40', text: 'text-blue-700 dark:text-blue-300', icon: PlayCircle, label: status };
      case 'pending':
        return { bg: 'bg-gov-cream dark:bg-surface-sunken', text: 'text-neutral-muted', icon: Clock, label: status };
      default:
        return { bg: 'bg-gov-cream dark:bg-surface-sunken', text: 'text-neutral-muted', icon: Clock, label: status };
    }
  })();
  const Icon = config.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${config.bg} ${config.text}`}>
      <Icon className='w-3 h-3' />
      {config.label}
    </span>
  );
}


function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  if (seconds < 1) return '<1s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const rem = Math.round(seconds % 60);
  if (mins < 60) return `${mins}m ${rem}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}
