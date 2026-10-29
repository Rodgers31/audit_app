/**
 * /admin/ingestion — list + filter ingestion jobs.
 *
 * Reads ``GET /api/v1/admin/ingestion-jobs`` with filters bound to
 * URL query params (``?domain=&status=&days=&page=``). Each row
 * links to /admin/ingestion/[jobId] for the detail view.
 */
'use client';

import PageShell from '@/components/admin/AdminPageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import styles from '@/components/admin/admin.module.css';
import { sourceLabel, sourceLabels } from '@/lib/admin/sourceLabels';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  XCircle,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect } from 'react';
import { activeJob, ingestionAge as timeAgo, ingestionFilters, parseIngestionList, type IngestionJobList } from '@/lib/admin/ingestion';
import { useOperationsAccess } from '@/lib/admin/ingestionPolling';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'completed', label: 'Completed' },
  { value: 'completed_with_errors', label: 'Completed w/ errors' },
  { value: 'failed', label: 'Failed' },
  { value: 'running', label: 'Running' },
  { value: 'pending', label: 'Pending' },
];

const DAYS_OPTIONS = [
  { value: 1, label: '24 hours' },
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
];

const PAGE_SIZE = 20;

export default function IngestionJobsPage() {
  return (
    <Suspense
      fallback={
        <PageShell title='Ingestion Jobs' subtitle='Loading…'>
          <div className='py-16 flex justify-center'>
            <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
          </div>
        </PageShell>
      }>
      <IngestionJobsInner />
    </Suspense>
  );
}

function IngestionJobsInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const access = useOperationsAccess(['ingestion-jobs']);
  const {domain,status,days,page,canonical} = ingestionFilters(new URLSearchParams(searchParams));
  const canonicalQuery = canonical.toString();
  const suppliedQuery = searchParams.toString();
  useEffect(() => {
    if (canonicalQuery !== suppliedQuery) router.replace(`/admin/ingestion${canonicalQuery ? '?' + canonicalQuery : ''}`);
  }, [canonicalQuery, suppliedQuery, router]);

  const setQuery = useCallback(
    (updates: Record<string, string | number | null>) => {
      const next = new URLSearchParams(canonicalQuery);
      for (const [k, v] of Object.entries(updates)) {
        if (v === null || v === '') next.delete(k);
        else next.set(k, String(v));
      }
      if (!('page' in updates)) next.delete('page');
      router.push(`/admin/ingestion${next.size ? '?' + next.toString() : ''}`);
    },
    [router, canonicalQuery]
  );

  const jobs = useQuery<IngestionJobList>({
    queryKey: ['admin', 'ingestion-jobs', access.actorId, { domain, status, days, page }],
    queryFn: async ({ signal }) => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE, days };
      if (domain) params.domain = domain;
      if (status) params.status = status;
      return parseIngestionList((await api.get('/admin/ingestion-jobs', { params, signal })).data, {page,page_size:PAGE_SIZE});
    },
    enabled: access.enabled,
    retry: false,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
    refetchInterval: query => access.enabled && !query.state.error && query.state.data?.jobs.some(activeJob) ? 15_000 : false,
  });

  const {isLoading,error,refetch,isFetching} = jobs;
  const data = access.isAdmin && !error ? jobs.data : undefined;
  if (!access.isAdmin) return <PageShell title='Ingestion Jobs'><p>{access.isLoading ? 'Verifying access…' : 'Admin access required.'}</p></PageShell>;

  return <PageShell title='Data updates' subtitle='Inspect recorded data jobs, then check their separate draft outcomes.' back={{href:'/admin',label:'Back to overview'}}>
    <div className={styles.workspace}>
      <section className={styles.panel} aria-label='Find data updates'><div className={styles.toolbar}>
        <div className={styles.filters}>
          <label>Source<select value={domain} onChange={e=>setQuery({domain:e.target.value})}><option value=''>All sources</option>{domain&&!Object.hasOwn(sourceLabels,domain)&&<option value={domain}>{sourceLabel(domain)}</option>}{Object.entries(sourceLabels).filter(([key])=>!['treasury','cob','oag','knbs','kra'].includes(key)).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
          <label>Outcome<select value={status} onChange={e=>setQuery({status:e.target.value})}>{STATUS_OPTIONS.map(opt=><option key={opt.value} value={opt.value}>{opt.label}</option>)}</select></label>
          <label>Time window<select value={days} onChange={e=>setQuery({days:Number(e.target.value)})}>{!DAYS_OPTIONS.some(opt=>opt.value===days)&&<option value={days}>Last {days} days</option>}{DAYS_OPTIONS.map(opt=><option key={opt.value} value={opt.value}>Last {opt.label}</option>)}</select></label>
        </div><div className={styles.filters}><button className={styles.button} disabled={!access.enabled||isFetching} onClick={()=>{if(access.enabled)void refetch();}}>Refresh updates</button>{(domain||status||days!==7)&&<button className={styles.button} onClick={()=>router.push('/admin/ingestion')}>Clear filters</button>}</div>
      </div></section>
      <section className={styles.panel} aria-labelledby='updates-heading'><div className={styles.sectionHeading}><div><h2 id='updates-heading'>Recorded jobs</h2><p>{data?`${data.total} matching jobs in the last ${days} days.`:'Current evidence is being checked.'} A completed data job does not establish that a draft was created.</p></div><Link className={styles.button} href='/admin/etl'>Run & recover a check</Link></div>
        {isLoading||(!data&&!error)?<p role='status'>Loading jobs…</p>:error?<div role='alert'><p>Could not load data updates. Their outcomes are unknown.</p><button className={styles.button} disabled={!access.enabled||isFetching} onClick={()=>{if(access.enabled)void refetch();}}>Retry</button></div>:!data?.jobs.length?<p>{page>1?'No jobs on this page.':'No jobs match these filters.'}</p>:<div className={styles.taskList}>{data.jobs.map(job=><article key={job.id} className={styles.job}>
          <div><Link href={`/admin/ingestion/${job.id}${canonicalQuery?'?'+canonicalQuery:''}`} className={styles.jobLink}>{sourceLabel(job.domain)}</Link><p className={styles.quiet}>Job #{job.id} · {job.status==='pending'?'Awaiting execution':timeAgo(job.started_at)}{job.dry_run?' · Dry run':''}</p></div>
          <div><StatusBadge status={job.status} hasErrors={job.error_count>0}/><p className={styles.quiet}>{formatDuration(job.duration_seconds)} · {job.error_count} errors</p></div>
          <div><strong>{job.items_created.toLocaleString()} created · {job.items_updated.toLocaleString()} updated</strong><p className={styles.quiet}>{job.items_processed.toLocaleString()} data items processed</p></div>
          <Link className={styles.button} href={`/admin/ingestion/${job.id}${canonicalQuery?'?'+canonicalQuery:''}`} aria-label={`Inspect outcome → ${sourceLabel(job.domain)} job #${job.id}`}>Inspect outcome →</Link>
        </article>)}</div>}
        {data&&!error&&(data.total>0||page>1)&&<Pagination page={page} pageSize={PAGE_SIZE} total={data.total} hasMore={data.has_more} onChange={p=>setQuery({page:p})}/>}
      </section>
    </div>
  </PageShell>;
}

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
        return {
          bg: 'bg-gov-copper/15',
          text: 'text-gov-copper dark:text-red-400',
          icon: XCircle,
          label: status,
        };
      case 'running':
        return {
          bg: 'bg-blue-100 dark:bg-blue-900/40',
          text: 'text-blue-700 dark:text-blue-300',
          icon: PlayCircle,
          label: status,
        };
      case 'pending':
        return {
          bg: 'bg-gov-cream dark:bg-surface-sunken',
          text: 'text-neutral-muted',
          icon: Clock,
          label: status,
        };
      default:
        return {
          bg: 'bg-gov-cream dark:bg-surface-sunken',
          text: 'text-neutral-muted',
          icon: Clock,
          label: status,
        };
    }
  })();
  const Icon = config.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${config.bg} ${config.text}`}>
      <Icon className='w-3 h-3' />
      {config.label}
    </span>
  );
}

function Pagination({
  page,
  pageSize,
  total,
  hasMore,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
  onChange: (page: number) => void;
}) {
  const start = Math.min((page - 1) * pageSize + 1, total);
  const end = Math.min(page * pageSize, total);
  return (
    <div className='flex items-center justify-between text-sm flex-wrap gap-3 pt-2'>
      <span className='text-neutral-muted'>
        Showing <span className='font-medium text-neutral-text'>{start.toLocaleString()}</span>–
        <span className='font-medium text-neutral-text'>{end.toLocaleString()}</span> of{' '}
        <span className='font-medium text-neutral-text'>{total.toLocaleString()}</span>
      </span>
      <div className='flex items-center gap-2'>
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className='inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text disabled:opacity-40 transition-all shadow-surface'>
          <ArrowLeft className='w-3.5 h-3.5' />
          Prev
        </button>
        <span className='text-neutral-muted text-xs'>Page {page}</span>
        <button
          onClick={() => onChange(page + 1)}
          disabled={!hasMore || page >= 10000}
          className='inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text disabled:opacity-40 transition-all shadow-surface'>
          Next
          <ArrowRight className='w-3.5 h-3.5' />
        </button>
      </div>
    </div>
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
