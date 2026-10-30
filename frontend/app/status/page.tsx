/**
 * System Status / Pipeline Health Dashboard
 *
 * Shows real-time data pipeline health: source connectivity,
 * auto-seeder status, database freshness, and any alerts.
 * Restricted to admin users only.
 */
'use client';

import AdminNav from '@/components/admin/AdminNav';
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
  Globe,
  Loader2,
  RefreshCcw,
  Server,
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

function Card({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <div className='bg-surface-base border border-neutral-border rounded-xl p-5 shadow-lg'>
      <div className='flex items-center gap-2 mb-4'>
        <Icon className='w-5 h-5 text-gov-gold' />
        <h3 className='text-neutral-text font-semibold text-base'>{title}</h3>
      </div>
      {children}
    </div>
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
      <AdminNav />
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

  return (
    <PageShell title='System Status'>
      <div className='max-w-5xl mx-auto space-y-6 pb-16 px-4 sm:px-6'>
        {/* ── Header row ── */}
        <div className='flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4'>
          <div className='flex items-center gap-3'>
            <StatusBadge status={data.status} />
            <span className='text-sm text-neutral-muted'>
              Database checked {timeAgo(data.checked_at)}
              {dataUpdatedAt
                ? ` · Refreshed ${timeAgo(new Date(dataUpdatedAt).toISOString())}`
                : ''}
            </span>
          </div>
          <button
            onClick={handleManualRefresh}
            disabled={manualRefreshing}
            className='inline-flex items-center gap-2 px-4 py-2 bg-surface-base border border-neutral-border hover:bg-surface-sunken text-neutral-text rounded-lg text-sm transition-colors disabled:opacity-50'>
            <RefreshCcw className={`w-4 h-4 ${manualRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* ── Alerts ── */}
        {alerts.length > 0 && (
          <Card
            title={`Alerts (${summary.errors} errors, ${summary.warnings} warnings)`}
            icon={AlertTriangle}>
            <ul className='space-y-2 max-h-64 overflow-y-auto'>
              {alerts.map((a, i) => (
                <li
                  key={i}
                  className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2 ${
                    a.level === 'error'
                      ? 'bg-red-500/10 text-red-800 dark:text-red-300'
                      : a.level === 'warning'
                        ? 'bg-amber-500/10 text-amber-800 dark:text-amber-300'
                        : 'bg-blue-500/10 text-blue-700 dark:text-blue-300'
                  }`}>
                  {a.level === 'error' ? (
                    <XCircle className='w-4 h-4 mt-0.5 shrink-0' />
                  ) : (
                    <AlertTriangle className='w-4 h-4 mt-0.5 shrink-0' />
                  )}
                  <span>
                    <strong className='font-medium'>[{a.source}]</strong> {a.message}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {/* ── Auto-Seeder ── */}
        <Card title='Web auto-seeder' icon={RefreshCcw}>
          <div className='grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4'>
            <Stat
              label='Status'
              value={auto_seeder?.is_running === true ? 'Running' : auto_seeder?.is_running === false ? 'Stopped' : 'Unavailable'}
              color={auto_seeder?.is_running ? 'text-emerald-800 dark:text-emerald-300' : 'text-neutral-muted'}
            />
            <Stat
              label='Total Fetches'
              // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- internal ops counter on an auth-gated page, not a published figure
              value={count(auto_seeder?.fetch_stats?.total_fetches)}
            />
            <Stat
              label='Successful'
              value={count(auto_seeder?.fetch_stats?.successful_fetches)}
              color='text-emerald-800 dark:text-emerald-300'
            />
            <Stat
              label='Failed'
              value={count(auto_seeder?.fetch_stats?.failed_fetches)}
              color={
                (auto_seeder?.fetch_stats?.failed_fetches ?? 0) > 0
                  ? 'text-red-800 dark:text-red-300'
                  : 'text-neutral-muted'
              }
            />
          </div>

          {/* Last refresh times */}
          {auto_seeder?.last_refresh && Object.keys(auto_seeder.last_refresh).length > 0 && (
            <div className='border-t border-gov-forest/20 pt-3'>
              <p className='text-xs text-neutral-muted mb-2 uppercase tracking-wide'>Last Refresh</p>
              <div className='grid grid-cols-2 sm:grid-cols-3 gap-2'>
                {Object.entries(auto_seeder.last_refresh).map(([domain, ts]) => (
                  <div key={domain} className='flex items-center gap-2 text-sm'>
                    <Clock className='w-3.5 h-3.5 text-neutral-muted' />
                    <span className='text-neutral-muted capitalize'>{domain}:</span>
                    <span className='text-neutral-text'>{timeAgo(ts)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Next refresh times */}
          {auto_seeder?.is_running && auto_seeder.next_refresh && Object.keys(auto_seeder.next_refresh).length > 0 && (
            <div className='border-t border-gov-forest/20 pt-3 mt-3'>
              <p className='text-xs text-neutral-muted mb-2 uppercase tracking-wide'>Next Refresh</p>
              <div className='grid grid-cols-2 sm:grid-cols-3 gap-2'>
                {Object.entries(auto_seeder.next_refresh).map(([domain, val]) => (
                  <div key={domain} className='flex items-center gap-2 text-sm'>
                    <Clock className='w-3.5 h-3.5 text-neutral-muted' />
                    <span className='text-neutral-muted capitalize'>{domain}:</span>
                    <span
                      className={`${val === 'Due now' || val === 'Never run' ? 'text-amber-800 dark:text-amber-300' : 'text-neutral-text'}`}>
                      {val === 'Due now' || val === 'Never run' ? val : timeAgo(val)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        {/* ── Database Stats ── */}
        <Card title='Database' icon={Database}>
          <div className='grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4'>
            <Stat label='Counties' value={count(database.entities?.counties)} target={database.entities ? '/47' : undefined} />
            <Stat label='Population Records' value={count(database.population?.records)} />
            <Stat
              label='Latest Pop. Year'
              value={
                database.population?.latest_year ? String(database.population.latest_year) : '—'
              }
            />
            <Stat
              label='Economic Indicators'
              value={count(database.economic_indicators?.records)}
            />
            <Stat label='Debt Categories' value={count(database.debt_categories?.records)} />
            <Stat label='Loans' value={count(database.loans?.records)} />
          </div>
        </Card>

        {/* ── Data Sources ── */}
        <Card title='Government Data Sources' icon={Globe}>
          <p className='text-xs text-neutral-muted mb-3'>Homepage observations only; these do not verify data freshness or ingestion. Checks run on demand, at most once per five minutes per web worker.</p>
          {data.source_checks_in_progress && <p role='status' className='text-sm text-gov-sage mb-3'>Checking source homepages independently…</p>}
          <div className='space-y-2'>
            {Object.values(sources).map((src) => (
              <div
                key={src.key}
                className='flex items-center justify-between bg-surface-sunken rounded-lg px-4 py-3'>
                <div className='flex items-center gap-3'>
                  {src.freshness === 'fresh' && src.reachable === true ? (
                    <CheckCircle2 className='w-4 h-4 text-emerald-800 dark:text-emerald-300' />
                  ) : (
                    <Clock className='w-4 h-4 text-neutral-muted' />
                  )}
                  <div>
                    <p className='text-sm text-neutral-text font-medium'>{src.name}</p>
                    <p className='text-xs text-neutral-text'>{src.url}</p>
                    {src.observed_at && <p className='text-xs text-neutral-text'>Observed {timeAgo(src.observed_at)}</p>}
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    src.freshness === 'fresh' && src.reachable === true
                      ? 'bg-emerald-500/15 text-emerald-800 dark:text-emerald-300'
                      : src.freshness === 'fresh' && src.reachable === false
                        ? 'bg-red-500/15 text-red-800 dark:text-red-300'
                        : 'bg-amber-500/15 text-amber-800 dark:text-amber-300'
                  }`}>
                  {sourceLabel(src)}
                </span>
              </div>
            ))}
            {Object.keys(sources).length === 0 && (
              <p className='text-sm text-neutral-muted'>No source checks available.</p>
            )}
          </div>
        </Card>

        <Card title='Execution evidence' icon={Server}>
          <p className='text-sm text-neutral-muted'>
            Dedicated worker execution is not checked here. The web pipeline is retired;
            homepage responses and calendar plans do not prove that a job ran.
          </p>
          <Link href='/admin/etl' className='inline-block mt-3 text-sm text-gov-sage dark:text-emerald-300 underline'>
            View dedicated worker readiness and command receipts
          </Link>
        </Card>

        {/* ── Footer note ── */}
        <p className='text-xs text-neutral-muted text-center pt-4'>
          Database observations refresh every 60 seconds and are cached for 30 seconds.
          Source observations are separate; stale or missing checks do not establish availability.
        </p>
      </div>
    </PageShell>
  );
}

/* ── Small stat component ── */
function Stat({
  label,
  value,
  color = 'text-neutral-text',
  target,
}: {
  label: string;
  value: string;
  color?: string;
  target?: string;
}) {
  return (
    <div>
      <p className='text-xs text-neutral-muted mb-0.5 font-medium'>{label}</p>
      <p className={`text-xl font-bold ${color}`}>
        {value}
        {target && <span className='text-sm text-neutral-muted font-normal'>{target}</span>}
      </p>
    </div>
  );
}
