/**
 * System Status / Pipeline Health Dashboard
 *
 * Shows real-time data pipeline health: source connectivity,
 * auto-seeder status, database freshness, and any alerts.
 * Restricted to admin users only.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
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
  Package,
  RefreshCcw,
  Server,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Alert {
  level: 'error' | 'warning' | 'info';
  source: string;
  message: string;
}

interface ModuleStatus {
  available: boolean;
  description: string;
  error?: string;
}

interface SourceCheck {
  key: string;
  name: string;
  url: string;
  reachable: boolean;
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
  status: 'healthy' | 'degraded' | 'unhealthy';
  checked_at: string;
  auto_seeder: SeederStatus;
  database: DatabaseStats;
  modules: Record<string, ModuleStatus>;
  sources: Record<string, SourceCheck>;
  etl_jobs: Array<{ job_id: string; status: string; source?: string }>;
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
      text: 'text-emerald-400',
      icon: CheckCircle2,
      label: 'Healthy',
    },
    degraded: {
      bg: 'bg-amber-500/15',
      text: 'text-amber-400',
      icon: AlertTriangle,
      label: 'Degraded',
    },
    unhealthy: { bg: 'bg-red-500/15', text: 'text-red-400', icon: XCircle, label: 'Unhealthy' },
  }[status] ?? { bg: 'bg-gray-500/15', text: 'text-gray-400 dark:text-neutral-muted/80', icon: Activity, label: status };

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
    <div className='bg-gov-dark border border-gov-forest/40 rounded-xl p-5 shadow-lg'>
      <div className='flex items-center gap-2 mb-4'>
        <Icon className='w-5 h-5 text-gov-gold' />
        <h3 className='text-white font-semibold text-base'>{title}</h3>
      </div>
      {children}
    </div>
  );
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
    queryFn: async () => {
      const res = await api.get('/system/pipeline-health');
      return res.data;
    },
    refetchInterval: 60_000, // auto-refresh every 60s
    staleTime: 30_000,
  });

  const handleManualRefresh = async () => {
    setManualRefreshing(true);
    await refetch();
    setManualRefreshing(false);
  };

  /* ---- Loading state ---- */
  if (isLoading) {
    return (
      <PageShell title='System Status'>
        <div className='flex flex-col items-center justify-center py-32 gap-3'>
          <Loader2 className='w-8 h-8 text-gov-sage animate-spin' />
          <p className='text-gov-sage/70'>Checking pipeline health…</p>
        </div>
      </PageShell>
    );
  }

  /* ---- Error state ---- */
  if (error || !data) {
    return (
      <PageShell title='System Status'>
        <div className='flex flex-col items-center justify-center py-32 gap-4'>
          <XCircle className='w-10 h-10 text-red-400' />
          <p className='text-red-300 text-center max-w-md'>
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

  const { auto_seeder, database, modules, sources, alerts, summary } = data;

  return (
    <PageShell title='System Status'>
      <div className='max-w-5xl mx-auto space-y-6 pb-16 px-4 sm:px-6'>
        {/* ── Header row ── */}
        <div className='flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4'>
          <div className='flex items-center gap-3'>
            <StatusBadge status={data.status} />
            <span className='text-sm text-gov-sage/60'>
              Checked {timeAgo(data.checked_at)}
              {dataUpdatedAt
                ? ` · Refreshed ${timeAgo(new Date(dataUpdatedAt).toISOString())}`
                : ''}
            </span>
          </div>
          <button
            onClick={handleManualRefresh}
            disabled={manualRefreshing}
            className='inline-flex items-center gap-2 px-4 py-2 bg-gov-forest/40 hover:bg-gov-forest/60 text-gov-sage rounded-lg text-sm transition-colors disabled:opacity-50'>
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
                      ? 'bg-red-500/10 text-red-300'
                      : a.level === 'warning'
                        ? 'bg-amber-500/10 text-amber-300'
                        : 'bg-blue-500/10 text-blue-300'
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
        <Card title='Auto-Seeder' icon={RefreshCcw}>
          <div className='grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4'>
            <Stat
              label='Status'
              value={auto_seeder.is_running ? 'Running' : 'Stopped'}
              color={auto_seeder.is_running ? 'text-emerald-400' : 'text-red-400'}
            />
            <Stat
              label='Total Fetches'
              value={String(auto_seeder.fetch_stats?.total_fetches ?? 0)}
            />
            <Stat
              label='Successful'
              value={String(auto_seeder.fetch_stats?.successful_fetches ?? 0)}
              color='text-emerald-400'
            />
            <Stat
              label='Failed'
              value={String(auto_seeder.fetch_stats?.failed_fetches ?? 0)}
              color={
                (auto_seeder.fetch_stats?.failed_fetches ?? 0) > 0
                  ? 'text-red-400'
                  : 'text-gov-sage/70'
              }
            />
          </div>

          {/* Last refresh times */}
          {auto_seeder.last_refresh && Object.keys(auto_seeder.last_refresh).length > 0 && (
            <div className='border-t border-gov-forest/20 pt-3'>
              <p className='text-xs text-gov-sage/50 mb-2 uppercase tracking-wide'>Last Refresh</p>
              <div className='grid grid-cols-2 sm:grid-cols-3 gap-2'>
                {Object.entries(auto_seeder.last_refresh).map(([domain, ts]) => (
                  <div key={domain} className='flex items-center gap-2 text-sm'>
                    <Clock className='w-3.5 h-3.5 text-gov-sage/40' />
                    <span className='text-gov-sage/70 capitalize'>{domain}:</span>
                    <span className='text-white'>{timeAgo(ts)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Next refresh times */}
          {auto_seeder.next_refresh && Object.keys(auto_seeder.next_refresh).length > 0 && (
            <div className='border-t border-gov-forest/20 pt-3 mt-3'>
              <p className='text-xs text-gov-sage/50 mb-2 uppercase tracking-wide'>Next Refresh</p>
              <div className='grid grid-cols-2 sm:grid-cols-3 gap-2'>
                {Object.entries(auto_seeder.next_refresh).map(([domain, val]) => (
                  <div key={domain} className='flex items-center gap-2 text-sm'>
                    <Clock className='w-3.5 h-3.5 text-gov-sage/40' />
                    <span className='text-gov-sage/70 capitalize'>{domain}:</span>
                    <span
                      className={`${val === 'Due now' || val === 'Never run' ? 'text-amber-400' : 'text-white'}`}>
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
            <Stat label='Counties' value={String(database.entities?.counties ?? 0)} target='/47' />
            <Stat label='Population Records' value={String(database.population?.records ?? 0)} />
            <Stat
              label='Latest Pop. Year'
              value={
                database.population?.latest_year ? String(database.population.latest_year) : '—'
              }
            />
            <Stat
              label='Economic Indicators'
              value={String(database.economic_indicators?.records ?? 0)}
            />
            <Stat label='Debt Categories' value={String(database.debt_categories?.records ?? 0)} />
            <Stat label='Loans' value={String(database.loans?.records ?? 0)} />
          </div>
        </Card>

        {/* ── Data Sources ── */}
        <Card title='Government Data Sources' icon={Globe}>
          <div className='space-y-2'>
            {Object.values(sources).map((src) => (
              <div
                key={src.key}
                className='flex items-center justify-between bg-gov-forest/30 rounded-lg px-4 py-3'>
                <div className='flex items-center gap-3'>
                  {src.reachable ? (
                    <CheckCircle2 className='w-4 h-4 text-emerald-400' />
                  ) : (
                    <XCircle className='w-4 h-4 text-red-400' />
                  )}
                  <div>
                    <p className='text-sm text-white font-medium'>{src.name}</p>
                    <p className='text-xs text-gov-sage/50'>{src.url}</p>
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    src.reachable
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-red-500/15 text-red-400'
                  }`}>
                  {src.reachable ? `OK (${src.status_code})` : src.error ? 'Timeout' : 'Down'}
                </span>
              </div>
            ))}
            {Object.keys(sources).length === 0 && (
              <p className='text-sm text-gov-sage/50'>No source checks available.</p>
            )}
          </div>
        </Card>

        {/* ── Module Availability ── */}
        <Card title='Pipeline Modules' icon={Package}>
          <div className='space-y-2'>
            {Object.entries(modules).map(([name, mod]) => (
              <div
                key={name}
                className='flex items-center justify-between bg-gov-forest/30 rounded-lg px-4 py-3'>
                <div className='flex items-center gap-3'>
                  {mod.available ? (
                    <CheckCircle2 className='w-4 h-4 text-emerald-400' />
                  ) : (
                    <AlertTriangle className='w-4 h-4 text-amber-400' />
                  )}
                  <div>
                    <p className='text-sm text-white font-medium'>{mod.description}</p>
                    <p className='text-xs text-gov-sage/50 font-mono'>{name}</p>
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    mod.available
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-amber-500/15 text-amber-400'
                  }`}>
                  {mod.available ? 'Loaded' : 'Unavailable'}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* ── Scheduled ETL Jobs ── */}
        <Card title='ETL Jobs' icon={Server}>
          {data.etl_jobs.length > 0 ? (
            <div className='space-y-2'>
              {data.etl_jobs.map((job) => (
                <div
                  key={job.job_id}
                  className='flex items-center justify-between bg-gov-forest/30 rounded-lg px-4 py-3'>
                  <div>
                    <p className='text-sm text-white font-medium'>{job.job_id}</p>
                    <p className='text-xs text-gov-sage/50'>{job.source ?? '—'}</p>
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      job.status === 'completed'
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : job.status === 'running'
                          ? 'bg-blue-500/15 text-blue-400'
                          : job.status === 'failed'
                            ? 'bg-red-500/15 text-red-400'
                            : 'bg-gray-500/15 text-gray-400 dark:text-neutral-muted/80'
                    }`}>
                    {job.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className='text-sm text-gov-sage/50'>
              No ETL jobs have been triggered yet. The APScheduler runs jobs automatically on a
              weekly/monthly cycle.
            </p>
          )}
        </Card>

        {/* ── Footer note ── */}
        <p className='text-xs text-gov-sage/40 text-center pt-4'>
          This page auto-refreshes every 60 seconds. Data is fetched from live government sources by
          the auto-seeder service.
        </p>
      </div>
    </PageShell>
  );
}

/* ── Small stat component ── */
function Stat({
  label,
  value,
  color = 'text-white',
  target,
}: {
  label: string;
  value: string;
  color?: string;
  target?: string;
}) {
  return (
    <div>
      <p className='text-xs text-gov-sage/70 mb-0.5 font-medium'>{label}</p>
      <p className={`text-xl font-bold ${color}`}>
        {value}
        {target && <span className='text-sm text-gov-sage/50 font-normal'>{target}</span>}
      </p>
    </div>
  );
}
