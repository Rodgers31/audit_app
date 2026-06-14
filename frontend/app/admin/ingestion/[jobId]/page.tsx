/**
 * /admin/ingestion/[jobId] — single-job detail view.
 *
 * Drill-in target from the ingestion list. Shows the full
 * ``IngestionJobResponse`` payload — every timing field, every
 * metric, the errors array, and the metadata blob.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  RefreshCcw,
  XCircle,
} from 'lucide-react';
import { use } from 'react';

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

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function IngestionJobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  const { data, isLoading, error, refetch, isFetching } = useQuery<IngestionJob>({
    queryKey: ['admin', 'ingestion-job', jobId],
    queryFn: async () => (await api.get(`/admin/ingestion-jobs/${jobId}`)).data,
    staleTime: 15_000,
  });

  if (isLoading) {
    return (
      <PageShell
        title={`Job #${jobId}`}
        back={{ href: '/admin/ingestion', label: 'Back to ingestion jobs' }}>
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
        back={{ href: '/admin/ingestion', label: 'Back to ingestion jobs' }}>
        <div className='py-16 flex flex-col items-center gap-3'>
          <XCircle className='w-10 h-10 text-gov-copper dark:text-red-400' />
          <p className='text-gov-copper dark:text-red-400 text-sm'>Job not found or failed to load.</p>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title={data.domain}
      subtitle={`Ingestion job #${data.id}`}
      back={{ href: '/admin/ingestion', label: 'Back to ingestion jobs' }}>
      <div className='space-y-5'>
        <div className='flex items-center justify-end'>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className='inline-flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text rounded-lg text-sm transition-all shadow-surface disabled:opacity-50'>
            <RefreshCcw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* ── Header card ── */}
        <motion.section
          variants={fadeUp}
          initial='hidden'
          animate='show'
          custom={0}
          className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl p-6 shadow-surface'>
          <div className='flex items-center gap-2 mb-4'>
            <StatusBadge status={data.status} hasErrors={data.errors.length > 0} />
            {data.dry_run && (
              <span className='text-[10px] uppercase tracking-wider bg-gov-warning/15 text-gov-warning dark:text-amber-300 px-1.5 py-0.5 rounded font-semibold'>
                dry-run
              </span>
            )}
          </div>

          <div className='grid grid-cols-2 sm:grid-cols-4 gap-5'>
            <Field label='Items processed' value={data.items_processed.toLocaleString()} big />
            <Field
              label='Created'
              value={data.items_created.toLocaleString()}
              tone='ok'
              big
            />
            <Field
              label='Updated'
              value={data.items_updated.toLocaleString()}
              tone='info'
              big
            />
            <Field
              label='Errors'
              value={data.errors.length.toString()}
              tone={data.errors.length > 0 ? 'bad' : 'muted'}
              big
            />
          </div>

          <div className='grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-neutral-border'>
            <Field label='Started' value={formatDate(data.started_at)} />
            <Field
              label='Finished'
              value={data.finished_at ? formatDate(data.finished_at) : '—'}
            />
            <Field label='Duration' value={formatDuration(data.duration_seconds)} />
            <Field label='Created at' value={formatDate(data.created_at)} />
          </div>
        </motion.section>

        {/* ── Errors ── */}
        {data.errors.length > 0 && (
          <motion.section
            variants={fadeUp}
            initial='hidden'
            animate='show'
            custom={1}
            className='bg-white dark:bg-surface-base border border-gov-copper/30 rounded-2xl p-5 shadow-surface'>
            <div className='flex items-center gap-2 mb-3'>
              <div className='w-7 h-7 rounded-lg bg-gov-copper/15 border border-gov-copper/25 flex items-center justify-center'>
                <AlertTriangle className='w-3.5 h-3.5 text-gov-copper dark:text-red-400' />
              </div>
              <h2 className='font-display text-lg text-neutral-text'>
                Errors ({data.errors.length})
              </h2>
            </div>
            <ul className='space-y-2'>
              {data.errors.map((err, i) => (
                <li
                  key={i}
                  className='bg-gov-copper/5 border border-gov-copper/20 rounded-lg p-3 text-xs font-mono text-gov-copper dark:text-red-400 overflow-x-auto'>
                  <pre className='whitespace-pre-wrap break-all'>
                    {typeof err === 'string' ? err : JSON.stringify(err, null, 2)}
                  </pre>
                </li>
              ))}
            </ul>
          </motion.section>
        )}

        {/* ── Metadata ── */}
        {Object.keys(data.metadata).length > 0 && (
          <motion.section
            variants={fadeUp}
            initial='hidden'
            animate='show'
            custom={2}
            className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl p-5 shadow-surface'>
            <h2 className='font-display text-lg text-neutral-text mb-3'>Metadata</h2>
            <pre className='text-xs font-mono bg-gov-cream dark:bg-surface-sunken border border-neutral-border rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all text-neutral-text'>
              {JSON.stringify(data.metadata, null, 2)}
            </pre>
          </motion.section>
        )}
      </div>
    </PageShell>
  );
}

/* ── Helpers ── */

function Field({
  label,
  value,
  tone = 'default',
  big = false,
}: {
  label: string;
  value: string;
  tone?: 'ok' | 'bad' | 'info' | 'muted' | 'default';
  big?: boolean;
}) {
  const colour = {
    ok: 'text-emerald-600 dark:text-emerald-400',
    bad: 'text-gov-copper dark:text-red-400',
    info: 'text-blue-600 dark:text-blue-400',
    muted: 'text-neutral-muted',
    default: 'text-neutral-text',
  }[tone];
  return (
    <div>
      <p className='text-[10px] uppercase tracking-wider text-neutral-muted font-semibold'>
        {label}
      </p>
      <p
        className={`mt-1 ${
          big ? 'text-2xl font-bold font-display' : 'text-sm font-medium'
        } ${colour}`}>
        {value}
      </p>
    </div>
  );
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

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
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
