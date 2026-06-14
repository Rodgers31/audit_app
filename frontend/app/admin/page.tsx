/**
 * /admin — admin overview dashboard.
 *
 * Top-level landing page for admins. Aggregates a few "what's the
 * system doing right now?" widgets pulled from the existing backend
 * admin endpoints — ingestion jobs, ETL schedule, ETL health, user
 * counts, and recent admin actions. Each card answers a single
 * question and links to the sub-page where the operator can drill
 * in. Wrapped in <PageShell> for the dark hero band that matches
 * the rest of the public site's chrome.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  History,
  Loader2,
  ListChecks,
  PlayCircle,
  TrendingUp,
  Users,
  XCircle,
} from 'lucide-react';
import Link from 'next/link';

/* ── API response shapes ── */
interface IngestionStats {
  total_jobs: number;
  completed: number;
  failed: number;
  running: number;
  pending: number;
  completed_with_errors: number;
  total_items_processed: number;
  total_items_created: number;
  total_items_updated: number;
  domains: Record<string, number>;
}

interface ScheduleSummary {
  timestamp: string;
  running_today: number;
  skipping_today: number;
  total_sources: number;
  efficiency: { skip_percentage: number; vs_fixed_schedule: string };
  sources_to_run: Array<{ source: string; reason: string }>;
}

interface EtlHealth {
  timestamp: string;
  scheduler_status: string;
  schedule_summary: unknown;
}

interface UserStats {
  total_users: number;
  admin_users: number;
  new_last_7_days: number;
  new_last_30_days: number;
}

interface AuditEntry {
  id: number;
  actor_id: string;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

interface AuditList {
  entries: AuditEntry[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

interface FailedJob {
  id: number;
  domain: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  errors: Array<{ message?: string; type?: string } | string>;
  created_at: string;
}

interface FailedJobList {
  jobs: FailedJob[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function AdminOverviewPage() {
  const ingestion = useQuery<IngestionStats>({
    queryKey: ['admin', 'ingestion-stats', 7],
    queryFn: async () =>
      (await api.get('/admin/ingestion-jobs/stats/summary', { params: { days: 7 } })).data,
    staleTime: 30_000,
  });

  const schedule = useQuery<ScheduleSummary>({
    queryKey: ['admin', 'etl-schedule-summary'],
    queryFn: async () => (await api.get('/admin/etl/schedule/summary')).data,
    staleTime: 60_000,
  });

  const health = useQuery<EtlHealth>({
    queryKey: ['admin', 'etl-health'],
    queryFn: async () => (await api.get('/admin/etl/health')).data,
    staleTime: 60_000,
  });

  const userStats = useQuery<UserStats>({
    queryKey: ['admin', 'user-stats'],
    queryFn: async () => (await api.get('/admin/users/stats')).data,
    staleTime: 60_000,
  });

  const recentActions = useQuery<AuditList>({
    queryKey: ['admin', 'audit-log', { recent: true }],
    queryFn: async () =>
      (await api.get('/admin/audit-log', { params: { page_size: 5, days: 30 } })).data,
    staleTime: 30_000,
  });

  const failedJobs = useQuery<FailedJobList>({
    queryKey: ['admin', 'ingestion-jobs', 'failed'],
    queryFn: async () =>
      (
        await api.get('/admin/ingestion-jobs', {
          params: { status: 'failed', days: 7, page_size: 5 },
        })
      ).data,
    staleTime: 30_000,
    // Refetch every 60s so the alerts banner reflects new failures without
    // a full page reload.
    refetchInterval: 60_000,
  });

  // Anything we surface to the admin as an unresolved problem. Keep this
  // tightly scoped — the banner should only appear when there's something
  // genuinely actionable, otherwise it becomes noise.
  const alerts: { kind: 'failed-jobs' | 'unhealthy-etl'; count?: number }[] = [];
  if (failedJobs.data && failedJobs.data.total > 0) {
    alerts.push({ kind: 'failed-jobs', count: failedJobs.data.total });
  }
  if (
    health.data &&
    health.data.scheduler_status &&
    health.data.scheduler_status !== 'healthy'
  ) {
    alerts.push({ kind: 'unhealthy-etl' });
  }

  return (
    <PageShell
      title='Admin Overview'
      subtitle='Monitor users, ingestion, ETL schedule and system health at a glance.'>
      <div className='space-y-8'>
        {/* ── Alerts banner ──
             Only renders when there's something actionable. Red so it
             reads instantly and the admin doesn't mistake "no alerts
             card" for "everything is healthy". */}
        {alerts.length > 0 && (
          <motion.section
            variants={fadeUp}
            initial='hidden'
            animate='show'
            custom={0}
            role='alert'
            className='rounded-2xl border-2 border-gov-copper/40 dark:border-red-500/40 bg-gov-copper/8 dark:bg-red-900/30 px-5 py-4 sm:px-6 sm:py-5 shadow-surface'>
            <div className='flex items-start gap-3'>
              <span className='inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gov-copper/15 dark:bg-red-500/20'>
                <AlertTriangle className='w-5 h-5 text-gov-copper dark:text-red-300' />
              </span>
              <div className='min-w-0 flex-1'>
                <div className='flex items-center gap-2 mb-1'>
                  <h2 className='text-base font-bold text-gov-copper dark:text-red-200'>
                    System needs attention
                  </h2>
                  <span className='inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-gov-copper/20 dark:bg-red-500/30 text-gov-copper dark:text-red-100'>
                    {alerts.length} {alerts.length === 1 ? 'alert' : 'alerts'}
                  </span>
                </div>
                <ul className='space-y-1.5 text-sm'>
                  {alerts.map((a) => (
                    <li key={a.kind} className='flex items-center gap-2 flex-wrap'>
                      {a.kind === 'failed-jobs' && (
                        <>
                          <span className='text-gov-copper/90 dark:text-red-100/90'>
                            <strong className='font-semibold'>{a.count}</strong>{' '}
                            ingestion {a.count === 1 ? 'job has' : 'jobs have'} failed in
                            the last 7 days.
                          </span>
                          <Link
                            href='/admin/ingestion?status=failed'
                            className='inline-flex items-center gap-1 text-xs font-semibold text-gov-copper dark:text-red-200 underline underline-offset-2 hover:text-gov-copper/80 dark:hover:text-red-100'>
                            View failures
                            <ArrowRight className='w-3 h-3' />
                          </Link>
                        </>
                      )}
                      {a.kind === 'unhealthy-etl' && (
                        <>
                          <span className='text-gov-copper/90 dark:text-red-100/90'>
                            ETL scheduler reports{' '}
                            <strong className='font-mono font-semibold'>
                              {health.data?.scheduler_status}
                            </strong>
                            .
                          </span>
                          <Link
                            href='/status'
                            className='inline-flex items-center gap-1 text-xs font-semibold text-gov-copper dark:text-red-200 underline underline-offset-2 hover:text-gov-copper/80 dark:hover:text-red-100'>
                            Check pipeline status
                            <ArrowRight className='w-3 h-3' />
                          </Link>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </motion.section>
        )}

        {/* ── Top stat grid ── */}
        <section>
          <SectionHeader icon={TrendingUp} title='At a glance' />
          <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4'>
            <StatCard
              order={0}
              title='Ingestion (last 7 days)'
              icon={ListChecks}
              query={ingestion}
              href='/admin/ingestion'
              renderValue={(d) => (
                <>
                  <BigNumber value={d.total_jobs} label='jobs' />
                  <SubStatRow>
                    <SubStat label='completed' value={d.completed} tone='ok' />
                    {d.completed_with_errors > 0 && (
                      <SubStat
                        label='w/ errors'
                        value={d.completed_with_errors}
                        tone='warn'
                      />
                    )}
                    <SubStat
                      label='failed'
                      value={d.failed}
                      tone={d.failed > 0 ? 'bad' : 'muted'}
                    />
                    {d.running > 0 && (
                      <SubStat label='running' value={d.running} tone='info' />
                    )}
                  </SubStatRow>
                </>
              )}
            />

            <StatCard
              order={1}
              title='ETL today'
              icon={PlayCircle}
              query={schedule}
              href='/admin/etl'
              renderValue={(d) => (
                <>
                  <BigNumber
                    value={`${d.running_today}/${d.total_sources}`}
                    label='sources running'
                  />
                  <p className='text-[11px] text-neutral-muted mt-3 line-clamp-1'>
                    {d.efficiency.vs_fixed_schedule}
                  </p>
                </>
              )}
            />

            <StatCard
              order={2}
              title='ETL system health'
              icon={Activity}
              query={health}
              href='/status'
              renderValue={(d) => {
                const ok = d.scheduler_status === 'healthy';
                return (
                  <>
                    <div className='flex items-center gap-2'>
                      {ok ? (
                        <CheckCircle2 className='w-7 h-7 text-emerald-500' />
                      ) : (
                        <XCircle className='w-7 h-7 text-gov-copper dark:text-red-400' />
                      )}
                      <span className='text-2xl font-bold text-neutral-text capitalize'>
                        {d.scheduler_status.split(':')[0]}
                      </span>
                    </div>
                    <p className='text-[11px] text-neutral-muted mt-3'>
                      Updated {timeAgo(d.timestamp)}
                    </p>
                  </>
                );
              }}
            />

            <StatCard
              order={3}
              title='Users'
              icon={Users}
              query={userStats}
              href='/admin/users'
              renderValue={(d) => (
                <>
                  <BigNumber value={d.total_users} label='total' />
                  <SubStatRow>
                    <SubStat label='admins' value={d.admin_users} tone='info' />
                    <SubStat label='new this week' value={d.new_last_7_days} tone='ok' />
                  </SubStatRow>
                </>
              )}
            />
          </div>
        </section>

        {/* ── Recent failures ──
             Always rendered when there are failures so the admin can
             click straight through to the offending job. Hidden when
             everything's clean to keep the page calm. */}
        {failedJobs.data && failedJobs.data.jobs.length > 0 && (
          <motion.section
            variants={fadeUp}
            initial='hidden'
            animate='show'
            custom={3}
            className='bg-white dark:bg-surface-base rounded-2xl p-5 sm:p-6 border-2 border-gov-copper/30 dark:border-red-500/30 shadow-surface'>
            <div className='flex items-center justify-between mb-4'>
              <div className='flex items-center gap-2'>
                <span className='inline-flex h-7 w-7 items-center justify-center rounded-lg bg-gov-copper/15 dark:bg-red-500/20'>
                  <XCircle className='w-4 h-4 text-gov-copper dark:text-red-300' />
                </span>
                <div>
                  <h2 className='text-base font-bold text-neutral-text leading-tight'>
                    Recent failures
                  </h2>
                  <p className='text-xs text-neutral-muted'>
                    Last {failedJobs.data.jobs.length} of {failedJobs.data.total} failed
                    {failedJobs.data.total === 1 ? ' job' : ' jobs'} in the last 7 days.
                  </p>
                </div>
              </div>
              <Link
                href='/admin/ingestion?status=failed'
                className='text-xs text-gov-copper dark:text-red-300 hover:text-gov-copper/80 dark:hover:text-red-200 inline-flex items-center gap-1 font-medium'>
                View all
                <ArrowRight className='w-3 h-3' />
              </Link>
            </div>
            <ul className='space-y-2'>
              {failedJobs.data.jobs.map((job) => {
                const firstError = job.errors?.[0];
                const errorMessage =
                  typeof firstError === 'string'
                    ? firstError
                    : firstError?.message || 'Unknown error';
                return (
                  <li key={job.id}>
                    <Link
                      href={`/admin/ingestion/${job.id}`}
                      className='group flex items-start gap-3 px-3 py-2.5 rounded-lg bg-gov-copper/5 dark:bg-red-900/20 hover:bg-gov-copper/10 dark:hover:bg-red-900/30 ring-1 ring-inset ring-gov-copper/15 dark:ring-red-500/25 transition-colors'>
                      <span className='shrink-0 mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-md bg-gov-copper/15 dark:bg-red-500/25'>
                        <XCircle className='w-3 h-3 text-gov-copper dark:text-red-300' />
                      </span>
                      <div className='min-w-0 flex-1'>
                        <div className='flex items-center gap-2 flex-wrap'>
                          <span className='text-xs font-mono font-semibold text-gov-copper dark:text-red-200'>
                            {job.domain}
                          </span>
                          <span className='text-[10px] text-neutral-muted'>
                            #{job.id} · {timeAgo(job.started_at || job.created_at)}
                          </span>
                          {job.duration_seconds != null && (
                            <span className='text-[10px] text-neutral-muted'>
                              · ran {job.duration_seconds.toFixed(1)}s
                            </span>
                          )}
                        </div>
                        <p className='text-xs text-neutral-text mt-0.5 line-clamp-1'>
                          {errorMessage}
                        </p>
                      </div>
                      <ArrowRight className='shrink-0 w-3.5 h-3.5 text-neutral-muted group-hover:text-gov-copper dark:group-hover:text-red-300 mt-1 transition-colors' />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </motion.section>
        )}

        {/* ── Ingestion volume + by-domain ── */}
        {ingestion.data && (
          <motion.section
            variants={fadeUp}
            initial='hidden'
            animate='show'
            custom={4}
            className='bg-white dark:bg-surface-base rounded-2xl p-5 sm:p-6 border border-neutral-border shadow-surface'>
            <SectionHeader
              icon={TrendingUp}
              title='Ingestion volume'
              subtitle='Items processed by the seeder over the last 7 days.'
              padded
            />
            <div className='grid grid-cols-3 gap-4'>
              <Metric label='Items processed' value={ingestion.data.total_items_processed} />
              <Metric
                label='Created'
                value={ingestion.data.total_items_created}
                tone='ok'
              />
              <Metric
                label='Updated'
                value={ingestion.data.total_items_updated}
                tone='info'
              />
            </div>

            {Object.keys(ingestion.data.domains).length > 0 && (
              <>
                <p className='text-[10px] text-neutral-muted mt-6 mb-2 uppercase tracking-wider font-semibold'>
                  Jobs by domain
                </p>
                <div className='flex flex-wrap gap-2'>
                  {Object.entries(ingestion.data.domains)
                    .sort(([, a], [, b]) => b - a)
                    .map(([domain, count]) => (
                      <Link
                        key={domain}
                        href={`/admin/ingestion?domain=${encodeURIComponent(domain)}`}
                        className='inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gov-sage/10 hover:bg-gov-sage/20 dark:bg-gov-sage/20 dark:hover:bg-gov-sage/30 ring-1 ring-inset ring-gov-sage/20 dark:ring-gov-sage/30 text-xs font-medium text-gov-forest dark:text-emerald-200 transition-colors'>
                        <span className='font-mono'>{domain}</span>
                        <span className='text-neutral-muted'>·</span>
                        <span className='text-gov-sage font-semibold'>{count}</span>
                      </Link>
                    ))}
                </div>
              </>
            )}
          </motion.section>
        )}

        {/* ── Two-column: recent actions + sources scheduled ── */}
        <div className='grid grid-cols-1 lg:grid-cols-2 gap-5'>
          {/* Recent admin actions */}
          {recentActions.data && recentActions.data.entries.length > 0 && (
            <motion.section
              variants={fadeUp}
              initial='hidden'
              animate='show'
              custom={5}
              className='bg-white dark:bg-surface-base rounded-2xl p-5 sm:p-6 border border-neutral-border shadow-surface'>
              <div className='flex items-center justify-between mb-4'>
                <SectionHeader icon={History} title='Recent admin actions' inline />
                <Link
                  href='/admin/audit-log'
                  className='text-xs text-gov-sage hover:text-gov-forest dark:hover:text-emerald-200 inline-flex items-center gap-1 font-medium'>
                  View all
                  <ArrowRight className='w-3 h-3' />
                </Link>
              </div>
              <ul className='space-y-2'>
                {recentActions.data.entries.map((entry) => (
                  <li
                    key={entry.id}
                    className='flex items-center gap-3 px-3 py-2 rounded-lg bg-gov-cream dark:bg-surface-sunken text-sm'>
                    <span className='inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-white dark:bg-surface-base text-gov-forest dark:text-emerald-200 border border-gov-sage/20 dark:border-gov-sage/30'>
                      {entry.action}
                    </span>
                    {entry.target_type && (
                      <span className='text-xs text-neutral-muted truncate hidden sm:inline'>
                        on <span className='font-mono'>{entry.target_type}</span>
                      </span>
                    )}
                    <span className='text-xs text-neutral-muted ml-auto whitespace-nowrap'>
                      {entry.actor_email
                        ? entry.actor_email.split('@')[0]
                        : entry.actor_id.slice(0, 8) + '…'}{' '}
                      · {timeAgo(entry.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </motion.section>
          )}

          {/* Sources scheduled today */}
          {schedule.data && schedule.data.sources_to_run.length > 0 && (
            <motion.section
              variants={fadeUp}
              initial='hidden'
              animate='show'
              custom={6}
              className='bg-white dark:bg-surface-base rounded-2xl p-5 sm:p-6 border border-neutral-border shadow-surface'>
              <SectionHeader
                icon={Clock}
                title='Sources scheduled today'
                subtitle='Smart-scheduler decisions for the next ETL cycle.'
              />
              <ul className='space-y-2 mt-4'>
                {schedule.data.sources_to_run.map(({ source, reason }) => (
                  <li
                    key={source}
                    className='flex items-start justify-between gap-3 px-3 py-2 rounded-lg bg-gov-cream dark:bg-surface-sunken'>
                    <div>
                      <span className='text-sm font-mono font-semibold text-neutral-text'>
                        {source}
                      </span>
                      <p className='text-xs text-neutral-muted mt-0.5'>{reason}</p>
                    </div>
                    <PlayCircle className='w-4 h-4 text-gov-sage shrink-0 mt-0.5' />
                  </li>
                ))}
              </ul>
            </motion.section>
          )}
        </div>
      </div>
    </PageShell>
  );
}

/* ── Building blocks ── */

interface QueryLike<T> {
  data?: T;
  isLoading: boolean;
  error: unknown;
}

function StatCard<T>({
  title,
  icon: Icon,
  query,
  href,
  renderValue,
  order = 0,
}: {
  title: string;
  icon: React.ElementType;
  query: QueryLike<T>;
  href: string;
  renderValue: (data: T) => React.ReactNode;
  order?: number;
}) {
  return (
    <motion.div
      variants={fadeUp}
      initial='hidden'
      animate='show'
      custom={order}>
      <Link
        href={href}
        className='group block bg-white dark:bg-surface-base rounded-2xl p-5 border border-neutral-border shadow-surface hover:shadow-elevated hover:border-gov-sage/40 transition-all h-full'>
        <div className='flex items-center justify-between mb-3'>
          <div className='flex items-center gap-2.5'>
            <div className='w-8 h-8 rounded-lg bg-gov-sage/15 flex items-center justify-center border border-gov-sage/20'>
              <Icon className='w-4 h-4 text-gov-sage' />
            </div>
            <h3 className='text-[11px] font-semibold uppercase tracking-wider text-neutral-muted'>
              {title}
            </h3>
          </div>
          <ArrowRight className='w-4 h-4 text-neutral-muted/40 group-hover:text-gov-sage group-hover:translate-x-0.5 transition-all' />
        </div>

        {query.isLoading ? (
          <div className='flex items-center gap-2 text-neutral-muted text-sm h-16'>
            <Loader2 className='w-4 h-4 animate-spin' />
            Loading…
          </div>
        ) : query.error || !query.data ? (
          <div className='flex items-center gap-2 text-gov-warning dark:text-amber-300 text-sm h-16'>
            <AlertTriangle className='w-4 h-4' />
            Could not load
          </div>
        ) : (
          renderValue(query.data)
        )}
      </Link>
    </motion.div>
  );
}

function BigNumber({ value, label }: { value: string | number; label: string }) {
  return (
    <div className='flex items-baseline gap-2'>
      <span className='text-3xl font-bold text-neutral-text font-display'>{value}</span>
      <span className='text-xs text-neutral-muted'>{label}</span>
    </div>
  );
}

function SubStatRow({ children }: { children: React.ReactNode }) {
  return <div className='flex flex-wrap gap-x-3 gap-y-1 mt-3 text-[11px]'>{children}</div>;
}

function SubStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'ok' | 'bad' | 'warn' | 'info' | 'muted';
}) {
  // Each tone gets a darker shade for light mode (readable on cream)
  // and a lighter, more saturated shade for dark mode (readable on
  // gov-dark). Using -600 on a dark card produces almost-invisible
  // muddy text; -300/-400 pops without being neon.
  const colour = {
    ok: 'text-emerald-600 dark:text-emerald-400',
    bad: 'text-gov-copper dark:text-red-400',
    warn: 'text-gov-warning dark:text-amber-300',
    info: 'text-blue-600 dark:text-blue-400',
    muted: 'text-neutral-muted',
  }[tone];
  return (
    <span className={colour}>
      <span className='font-semibold'>{value}</span>{' '}
      <span className='text-neutral-muted'>{label}</span>
    </span>
  );
}

function Metric({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: number;
  tone?: 'ok' | 'info' | 'default';
}) {
  const colour = {
    ok: 'text-emerald-600 dark:text-emerald-400',
    info: 'text-blue-600 dark:text-blue-400',
    default: 'text-neutral-text',
  }[tone];
  return (
    <div>
      <p className='text-[10px] uppercase tracking-wider text-neutral-muted font-semibold'>
        {label}
      </p>
      <p className={`text-2xl font-bold mt-1 font-display ${colour}`}>
        {value.toLocaleString()}
      </p>
    </div>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  subtitle,
  inline = false,
  padded = false,
}: {
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  inline?: boolean;
  padded?: boolean;
}) {
  return (
    <div className={padded ? 'mb-4' : inline ? '' : 'mb-3'}>
      <div className='flex items-center gap-2'>
        <Icon className='w-4 h-4 text-gov-sage' />
        <h2 className='font-display text-lg text-neutral-text'>{title}</h2>
      </div>
      {subtitle && <p className='text-xs text-neutral-muted mt-0.5 ml-6'>{subtitle}</p>}
    </div>
  );
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return 'never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
