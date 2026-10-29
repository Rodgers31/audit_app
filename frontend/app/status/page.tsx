/**
 * System Status / Pipeline Health Dashboard
 *
 * Shows real-time data pipeline health: source connectivity,
 * auto-seeder status, database freshness, and any alerts.
 * Restricted to admin users only.
 */
'use client';

import styles from '@/components/admin/admin.module.css';
import PageShell from '@/components/admin/AdminPageShell';
import api from '@/lib/api/axios';
import { AdminGuard } from '@/lib/auth/admin';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  Loader2,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Alert {
  level: 'error' | 'warning' | 'info';
  source: string;
  message: string;
}

interface SourceCheck {
  key: string;
  name: string;
  url: string;
  freshness: 'unknown' | 'fresh' | 'stale';
  outcome: 'not_observed' | 'http_response' | 'timeout' | 'certificate_error' | 'request_error';
  reachable: boolean | null;
  observed_at?: string | null;
  status_code?: number;
  error?: string;
}

interface DatabaseStats {
  entities?: { total: number; counties: number; has_national: boolean };
  population?: { records: number; latest_year: number | null };
  economic_indicators?: { records: number; latest_year: number | null };
  debt_categories?: { records: number };
  loans?: { records: number };
  source_documents?: { records: number };
}

interface SeederStatus {
  is_running: boolean;
  last_refresh?: Record<string, string>;
  fetch_stats?: {
    total_fetches: number;
    successful_fetches: number;
    failed_fetches: number;
    last_full_refresh: string | null;
  };
  next_refresh?: Record<string, string>;
}

interface PipelineHealth {
  schema_version: 2;
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  checked_at: string;
  auto_seeder: SeederStatus | null;
  database: DatabaseStats;
  sources: Record<string, SourceCheck>;
  source_checks_in_progress: boolean;
  execution: { owner: string; status: 'not_observed'; evidence_url: string };
  alerts: Alert[];
  summary: { errors: number; warnings: number; total_alerts: number };
}

/* ------------------------------------------------------------------ */
/*  Helper components                                                  */
/* ------------------------------------------------------------------ */

function StatusBadge({ status }: { status: 'healthy' | 'degraded' | 'unhealthy' | string }) {
  const config = {
    healthy: {
      bg: 'bg-emerald-500/15',
      text: 'text-emerald-800 dark:text-emerald-300',
      icon: CheckCircle2,
      label: 'Observed checks healthy',
    },
    degraded: {
      bg: 'bg-amber-500/15',
      text: 'text-amber-800 dark:text-amber-300',
      icon: AlertTriangle,
      label: 'Degraded',
    },
    unknown: { bg: 'bg-gray-500/15', text: 'text-neutral-text', icon: Clock, label: 'Checks incomplete' },
    unhealthy: { bg: 'bg-red-500/15', text: 'text-red-800 dark:text-red-300', icon: XCircle, label: 'Unhealthy' },
  }[status] ?? { bg: 'bg-gray-500/15', text: 'text-neutral-muted', icon: Activity, label: status };

  const Icon = config.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium ${config.bg} ${config.text}`}>
      <Icon className='w-4 h-4' />
      {config.label}
    </span>
  );
}

function sourceLabel(src: SourceCheck): string {
  if (src.freshness === 'unknown' || src.reachable === null) return 'Not yet observed';
  const outcome = src.outcome === 'http_response' ? `HTTP ${src.status_code}` : {
    timeout: 'Timeout', certificate_error: 'Certificate error', request_error: 'Request failed',
    not_observed: 'Not yet observed',
  }[src.outcome];
  return src.freshness === 'stale' ? `Stale · ${outcome}` : outcome;
}

function count(value: number | undefined): string {
  return value === undefined ? 'Unavailable' : String(value);
}

function timeAgo(isoString: string | null | undefined): string {
  if (!isoString) return 'Never';
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

export default function StatusPage() {
  return (
    <AdminGuard>
      <StatusDashboard />
    </AdminGuard>
  );
}

function StatusDashboard() {
  const [manualRefreshing, setManualRefreshing] = useState(false);

  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery<PipelineHealth>({
    queryKey: ['pipeline-health'],
    queryFn: async ({ signal }) => {
      const res = await api.get('/system/pipeline-health/v2', { signal });
      if (res.data?.schema_version !== 2) throw new Error('Unsupported health snapshot');
      return res.data;
    },
    refetchInterval: (query) => query.state.data?.source_checks_in_progress ? 2_000 : 60_000,
    staleTime: 0,
  });

  const handleManualRefresh = async () => {
    setManualRefreshing(true);
    try { await refetch(); } finally { setManualRefreshing(false); }
  };

  /* ---- Loading state ---- */
  if (isLoading) {
    return (
      <PageShell title='System Status'>
        <div className='flex flex-col items-center justify-center py-32 gap-3'>
          <Loader2 className='w-8 h-8 text-gov-sage animate-spin' />
          <p className='text-neutral-muted'>Checking pipeline health…</p>
        </div>
      </PageShell>
    );
  }

  /* ---- Error state ---- */
  if (error || !data) {
    return (
      <PageShell title='System Status'>
        <div className='flex flex-col items-center justify-center py-32 gap-4'>
          <XCircle className='w-10 h-10 text-red-800 dark:text-red-300' />
          <p className='text-red-800 dark:text-red-300 text-center max-w-md'>
            Could not reach the backend. The server may be waking up — try again in a few seconds.
          </p>
          <button
            onClick={() => refetch()}
            className='px-4 py-2 bg-gov-sage/20 hover:bg-gov-sage/30 text-gov-sage rounded-lg text-sm transition-colors'>
            Retry
          </button>
        </div>
      </PageShell>
    );
  }

  const { auto_seeder, database, sources, alerts, summary } = data;

  return <PageShell title='System status' subtitle='Separate observed checks from worker execution and data freshness.' back={{href:'/admin',label:'Back to overview'}}>
    <div className={styles.workspace}>
      <section className={styles.panel}><div className={styles.sectionHeading}><div><h2>Observed checks</h2><p>Database checked {timeAgo(data.checked_at)}{dataUpdatedAt?` · fetched ${timeAgo(new Date(dataUpdatedAt).toISOString())}`:''}</p></div><button className={styles.button} disabled={manualRefreshing} onClick={handleManualRefresh}>Refresh observations</button></div><StatusBadge status={data.status}/><p className={`${styles.quiet} mt-4`}>This status describes the checks below. Dedicated worker execution is not checked here; homepage responses do not establish that a data job ran.</p><div className={`${styles.filters} mt-4`}><Link className={`${styles.button} ${styles.primary}`} href='/admin/etl'>Check worker & command receipts</Link><Link className={styles.button} href='/admin/ingestion'>Inspect data updates</Link></div></section>
      {alerts.length>0&&<section className={styles.notice} aria-labelledby='status-attention'><h2 id='status-attention'>Observed issues · {summary.errors} errors, {summary.warnings} warnings</h2><ul>{alerts.map((alert,i)=><li key={i} className='mt-3'><strong>{alert.source}</strong> · {alert.message}</li>)}</ul></section>}
      <section className={styles.panel}><div className={styles.sectionHeading}><div><h2>Government source homepages</h2><p>Homepage checks run on demand, at most once per five minutes per web worker. They do not verify the underlying figures or ingestion.</p></div></div>{data.source_checks_in_progress&&<p role='status'>Checking source homepages independently…</p>}<div className={styles.taskList}>{Object.values(sources).map(src=><article className={styles.task} key={src.key}><div className='min-w-0'><strong>{src.name}</strong><p className='break-all'>{src.url}</p><p>Observed {src.observed_at?timeAgo(src.observed_at):'not yet'}</p></div><span className={styles.taskAction}>{sourceLabel(src)}</span></article>)}</div>{!Object.keys(sources).length&&<p>No source checks are available. Their reachability is unknown.</p>}</section>
      <details className={styles.disclosure}><summary>Database record inventory</summary><div><p className={styles.quiet}>Stored row counts describe inventory. They do not establish current publication authority.</p><dl className={styles.facts}><div><dt>Counties</dt><dd>{count(database.entities?.counties)}</dd></div><div><dt>Population records</dt><dd>{count(database.population?.records)}</dd></div><div><dt>Latest population year</dt><dd>{database.population?.latest_year??'Unavailable'}</dd></div><div><dt>Economic indicators</dt><dd>{count(database.economic_indicators?.records)}</dd></div><div><dt>Debt categories</dt><dd>{count(database.debt_categories?.records)}</dd></div><div><dt>Loans</dt><dd>{count(database.loans?.records)}</dd></div></dl></div></details>
      <details className={styles.disclosure}><summary>Retired web auto-seeder diagnostics</summary><div><p>The web pipeline is retired. These process-local diagnostics are separate from the dedicated runner.</p><dl className={`${styles.facts} mt-4`}><div><dt>Local process state</dt><dd>{auto_seeder?.is_running===true?'Running':auto_seeder?.is_running===false?'Stopped':'Unavailable'}</dd></div><div><dt>Recorded fetches</dt><dd>{count(auto_seeder?.fetch_stats?.total_fetches)}</dd></div><div><dt>Recorded successes</dt><dd>{count(auto_seeder?.fetch_stats?.successful_fetches)}</dd></div><div><dt>Recorded failures</dt><dd>{count(auto_seeder?.fetch_stats?.failed_fetches)}</dd></div></dl></div></details>
      <p className={styles.quiet}>Database observations refresh every 60 seconds and are cached for 30 seconds. Stale or missing source observations do not establish availability.</p>
    </div>
  </PageShell>;
}
