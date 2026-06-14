/**
 * /admin/ingestion — list + filter ingestion jobs.
 *
 * Reads ``GET /api/v1/admin/ingestion-jobs`` with filters bound to
 * URL query params (``?domain=&status=&days=&page=``). Each row
 * links to /admin/ingestion/[jobId] for the detail view.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Clock,
  Loader2,
  Pause,
  PlayCircle,
  RefreshCcw,
  XCircle,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback } from 'react';

interface IngestionJob {
  id: number;
  domain: string;
  status: string;
  dry_run: boolean;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  items_processed: number;
  items_created: number;
  items_updated: number;
  errors: unknown[];
  metadata: Record<string, unknown>;
  created_at: string;
}

interface IngestionJobList {
  jobs: IngestionJob[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

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

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.03, ease: [0.22, 1, 0.36, 1] },
  }),
};

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

  const domain = searchParams.get('domain') ?? '';
  const status = searchParams.get('status') ?? '';
  const days = Number(searchParams.get('days') ?? '7');
  const page = Number(searchParams.get('page') ?? '1');

  const setQuery = useCallback(
    (updates: Record<string, string | number | null>) => {
      const next = new URLSearchParams(searchParams);
      for (const [k, v] of Object.entries(updates)) {
        if (v === null || v === '') next.delete(k);
        else next.set(k, String(v));
      }
      if (!('page' in updates)) next.delete('page');
      router.replace(`/admin/ingestion${next.size ? '?' + next.toString() : ''}`);
    },
    [router, searchParams]
  );

  const { data, isLoading, error, refetch, isFetching } = useQuery<IngestionJobList>({
    queryKey: ['admin', 'ingestion-jobs', { domain, status, days, page }],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE, days };
      if (domain) params.domain = domain;
      if (status) params.status = status;
      return (await api.get('/admin/ingestion-jobs', { params })).data;
    },
    staleTime: 15_000,
  });

  return (
    <PageShell
      title='Ingestion Jobs'
      subtitle={
        data
          ? `${data.total.toLocaleString()} job${data.total === 1 ? '' : 's'} in the last ${days} day${days === 1 ? '' : 's'}.`
          : 'Inspect what the data pipeline did recently.'
      }
      back={{ href: '/admin', label: 'Back to overview' }}>
      <div className='space-y-5'>
        {/* ── Filter bar ── */}
        <div className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl p-4 shadow-surface flex flex-wrap items-end gap-3'>
          <FilterField label='Domain'>
            <input
              type='text'
              value={domain}
              onChange={(e) => setQuery({ domain: e.target.value || null })}
              placeholder='e.g. counties_budget'
              className='w-48 px-3 py-1.5 text-sm rounded-lg border border-neutral-border focus:outline-none focus:ring-2 focus:ring-gov-sage/40 focus:border-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken'
            />
          </FilterField>
          <FilterField label='Status'>
            <select
              value={status}
              onChange={(e) => setQuery({ status: e.target.value || null })}
              className='w-52 px-3 py-1.5 text-sm rounded-lg border border-neutral-border focus:outline-none focus:ring-2 focus:ring-gov-sage/40 focus:border-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken'>
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </FilterField>
          <FilterField label='Time window'>
            <select
              value={days}
              onChange={(e) => setQuery({ days: e.target.value })}
              className='w-40 px-3 py-1.5 text-sm rounded-lg border border-neutral-border focus:outline-none focus:ring-2 focus:ring-gov-sage/40 focus:border-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken'>
              {DAYS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  Last {opt.label}
                </option>
              ))}
            </select>
          </FilterField>
          <div className='ml-auto flex items-center gap-2'>
            {(domain || status || days !== 7) && (
              <button
                onClick={() => router.replace('/admin/ingestion')}
                className='text-xs text-neutral-muted hover:text-neutral-text underline underline-offset-2 px-2'>
                Clear filters
              </button>
            )}
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className='inline-flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text rounded-lg text-sm transition-all shadow-surface disabled:opacity-50'>
              <RefreshCcw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* ── Body ── */}
        {isLoading ? (
          <BodyState>
            <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
            <p className='text-neutral-muted text-sm'>Loading jobs…</p>
          </BodyState>
        ) : error ? (
          <BodyState>
            <XCircle className='w-8 h-8 text-gov-copper dark:text-red-400' />
            <p className='text-gov-copper dark:text-red-400 text-sm'>Could not load jobs.</p>
            <button
              onClick={() => refetch()}
              className='px-3 py-1.5 bg-gov-sage/10 hover:bg-gov-sage/20 text-gov-forest dark:text-emerald-200 rounded-lg text-sm transition-colors'>
              Retry
            </button>
          </BodyState>
        ) : !data || data.jobs.length === 0 ? (
          <BodyState>
            <Pause className='w-8 h-8 text-neutral-muted/40' />
            <p className='text-neutral-muted text-sm'>No jobs match these filters.</p>
          </BodyState>
        ) : (
          <>
            <div className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl overflow-hidden shadow-surface'>
              {/* Desktop table */}
              <table className='hidden md:table w-full text-sm'>
                <thead className='bg-gov-cream dark:bg-surface-sunken border-b border-neutral-border text-[11px] uppercase tracking-wider text-neutral-muted'>
                  <tr>
                    <th className='px-4 py-3 text-left font-semibold'>Domain</th>
                    <th className='px-4 py-3 text-left font-semibold'>Status</th>
                    <th className='px-4 py-3 text-left font-semibold'>Started</th>
                    <th className='px-4 py-3 text-right font-semibold'>Duration</th>
                    <th className='px-4 py-3 text-right font-semibold'>Items</th>
                    <th className='px-4 py-3 text-right font-semibold'>Created</th>
                    <th className='px-4 py-3 text-right font-semibold'>Updated</th>
                    <th className='px-2 py-3'></th>
                  </tr>
                </thead>
                <tbody>
                  {data.jobs.map((job, i) => (
                    <motion.tr
                      key={job.id}
                      variants={fadeUp}
                      initial='hidden'
                      animate='show'
                      custom={i}
                      onClick={() => router.push(`/admin/ingestion/${job.id}`)}
                      className='border-b last:border-0 border-neutral-border/60 hover:bg-gov-cream/60 dark:hover:bg-surface-elevated cursor-pointer transition-colors group'>
                      <td className='px-4 py-3'>
                        <div className='flex items-center gap-2'>
                          <span className='font-mono text-xs font-semibold text-neutral-text'>
                            {job.domain}
                          </span>
                          {job.dry_run && (
                            <span className='text-[9px] uppercase tracking-wider bg-gov-warning/15 text-gov-warning dark:text-amber-300 px-1.5 py-0.5 rounded font-semibold'>
                              dry-run
                            </span>
                          )}
                        </div>
                      </td>
                      <td className='px-4 py-3'>
                        <StatusBadge status={job.status} hasErrors={job.errors.length > 0} />
                      </td>
                      <td className='px-4 py-3 text-neutral-muted whitespace-nowrap'>
                        {timeAgo(job.started_at)}
                      </td>
                      <td className='px-4 py-3 text-right text-neutral-muted whitespace-nowrap'>
                        {formatDuration(job.duration_seconds)}
                      </td>
                      <td className='px-4 py-3 text-right text-neutral-text font-medium'>
                        {job.items_processed.toLocaleString()}
                      </td>
                      <td className='px-4 py-3 text-right text-emerald-600 dark:text-emerald-400 font-medium'>
                        {job.items_created.toLocaleString()}
                      </td>
                      <td className='px-4 py-3 text-right text-blue-600 dark:text-blue-400 font-medium'>
                        {job.items_updated.toLocaleString()}
                      </td>
                      <td className='px-2 py-3'>
                        <ChevronRight className='w-4 h-4 text-neutral-muted/40 group-hover:text-gov-sage group-hover:translate-x-0.5 transition-all' />
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>

              {/* Mobile card list */}
              <ul className='md:hidden divide-y divide-neutral-border/60'>
                {data.jobs.map((job, i) => (
                  <motion.li
                    key={job.id}
                    variants={fadeUp}
                    initial='hidden'
                    animate='show'
                    custom={i}>
                    <Link
                      href={`/admin/ingestion/${job.id}`}
                      className='block px-4 py-3 hover:bg-gov-cream/60 dark:hover:bg-surface-elevated transition-colors'>
                      <div className='flex items-center justify-between gap-2 mb-1'>
                        <span className='font-mono text-xs font-semibold text-neutral-text'>
                          {job.domain}
                        </span>
                        <StatusBadge status={job.status} hasErrors={job.errors.length > 0} />
                      </div>
                      <div className='flex items-center justify-between text-xs text-neutral-muted'>
                        <span>{timeAgo(job.started_at)}</span>
                        <span>{formatDuration(job.duration_seconds)}</span>
                      </div>
                      <div className='flex items-center gap-3 text-xs mt-1'>
                        <span className='text-neutral-muted'>
                          {job.items_processed.toLocaleString()} processed
                        </span>
                        <span className='text-emerald-600 dark:text-emerald-400 font-medium'>
                          +{job.items_created.toLocaleString()}
                        </span>
                        <span className='text-blue-600 dark:text-blue-400 font-medium'>
                          ~{job.items_updated.toLocaleString()}
                        </span>
                      </div>
                    </Link>
                  </motion.li>
                ))}
              </ul>
            </div>

            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              hasMore={data.has_more}
              onChange={(p) => setQuery({ page: p })}
            />
          </>
        )}
      </div>
    </PageShell>
  );
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
              label: 'completed*',
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

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className='flex flex-col'>
      <label className='text-[10px] uppercase tracking-wider text-neutral-muted font-semibold mb-1'>
        {label}
      </label>
      {children}
    </div>
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
  const start = (page - 1) * pageSize + 1;
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
          disabled={!hasMore}
          className='inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text disabled:opacity-40 transition-all shadow-surface'>
          Next
          <ArrowRight className='w-3.5 h-3.5' />
        </button>
      </div>
    </div>
  );
}

function BodyState({ children }: { children: React.ReactNode }) {
  return (
    <div className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl py-16 flex flex-col items-center justify-center gap-3 shadow-surface'>
      {children}
    </div>
  );
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
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
