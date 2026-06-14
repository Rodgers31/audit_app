/**
 * /admin/etl — ETL schedule + manual trigger.
 *
 * Reads /admin/etl/schedule + /admin/etl/health to show what the
 * smart scheduler is doing today, and exposes per-source "trigger
 * now" buttons that POST to /admin/etl/trigger/{source}.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  RefreshCcw,
  XCircle,
  Zap,
} from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

interface ScheduleSourceDecision {
  should_run: boolean;
  reason: string;
  next_run: string | null;
  next_reason?: string;
  current_period?: string;
}

interface ScheduleResponse {
  timestamp: string;
  summary: {
    sources_running_today: number;
    sources_skipping_today: number;
    total_sources: number;
    skip_percentage: number;
    efficiency_vs_fixed_schedule: string;
    sources_to_run: Array<{ source: string; reason: string }>;
    sources_not_running: string[];
  };
  sources: Record<string, ScheduleSourceDecision>;
}

interface EtlHealth {
  timestamp: string;
  scheduler_status: string;
  schedule_summary: unknown;
}

interface TriggerResponse {
  ok: boolean;
  job_id: number;
  source: string;
  status: string;
  dry_run: boolean;
  note: string;
}

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function AdminEtlPage() {
  const qc = useQueryClient();

  const schedule = useQuery<ScheduleResponse>({
    queryKey: ['admin', 'etl-schedule'],
    queryFn: async () => (await api.get('/admin/etl/schedule')).data,
    staleTime: 30_000,
  });

  const health = useQuery<EtlHealth>({
    queryKey: ['admin', 'etl-health'],
    queryFn: async () => (await api.get('/admin/etl/health')).data,
    staleTime: 30_000,
  });

  const trigger = useMutation<TriggerResponse, unknown, { source: string; dryRun: boolean }>({
    mutationFn: async ({ source, dryRun }) =>
      (await api.post(`/admin/etl/trigger/${source}`, { dry_run: dryRun })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'etl-schedule'] });
      qc.invalidateQueries({ queryKey: ['admin', 'ingestion-jobs'] });
      qc.invalidateQueries({ queryKey: ['admin', 'ingestion-stats'] });
    },
  });

  return (
    <PageShell
      title='ETL Schedule'
      subtitle='Smart-scheduler decisions for today, plus manual trigger controls per source.'
      back={{ href: '/admin', label: 'Back to overview' }}>
      <div className='space-y-5'>
        <div className='flex items-center justify-end'>
          <button
            onClick={() => {
              schedule.refetch();
              health.refetch();
            }}
            className='inline-flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text rounded-lg text-sm transition-all shadow-surface'>
            <RefreshCcw
              className={`w-4 h-4 ${
                schedule.isFetching || health.isFetching ? 'animate-spin' : ''
              }`}
            />
            Refresh
          </button>
        </div>

        {/* ── Summary cards ── */}
        <div className='grid grid-cols-1 md:grid-cols-3 gap-4'>
          <SummaryCard
            order={0}
            icon={PlayCircle}
            label='Running today'
            value={
              schedule.data
                ? `${schedule.data.summary.sources_running_today}/${schedule.data.summary.total_sources}`
                : '…'
            }
          />
          <SummaryCard
            order={1}
            icon={Activity}
            label='Scheduler health'
            value={health.data ? health.data.scheduler_status.split(':')[0] : '…'}
            valueClassName='capitalize'
          />
          <SummaryCard
            order={2}
            icon={Zap}
            label='Efficiency vs fixed'
            value={schedule.data?.summary.efficiency_vs_fixed_schedule ?? '—'}
            small
          />
        </div>

        {/* ── Trigger feedback ── */}
        {trigger.isSuccess && trigger.data && (
          <motion.div
            variants={fadeUp}
            initial='hidden'
            animate='show'
            className='bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 rounded-2xl px-4 py-3 flex items-start gap-2.5 text-sm shadow-surface'>
            <CheckCircle2 className='w-5 h-5 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0' />
            <div>
              <p className='font-semibold text-emerald-900 dark:text-emerald-200'>
                Queued <span className='font-mono'>{trigger.data.source}</span> · job #
                <Link
                  href={`/admin/ingestion/${trigger.data.job_id}`}
                  className='underline underline-offset-2 hover:text-emerald-700 dark:text-emerald-300'>
                  {trigger.data.job_id}
                </Link>
                {trigger.data.dry_run && ' (dry-run)'}
              </p>
              <p className='text-emerald-800/80 text-xs mt-0.5'>{trigger.data.note}</p>
            </div>
          </motion.div>
        )}
        {trigger.isError && (
          <motion.div
            variants={fadeUp}
            initial='hidden'
            animate='show'
            className='bg-gov-copper/10 border border-gov-copper/30 rounded-2xl px-4 py-3 flex items-start gap-2.5 text-sm shadow-surface'>
            <XCircle className='w-5 h-5 text-gov-copper dark:text-red-400 mt-0.5 shrink-0' />
            <p className='text-gov-copper dark:text-red-400'>
              Failed to queue trigger:{' '}
              {(trigger.error as { response?: { data?: { detail?: string } } })?.response?.data
                ?.detail || 'unknown error'}
            </p>
          </motion.div>
        )}

        {/* ── Per-source list ── */}
        <motion.section
          variants={fadeUp}
          initial='hidden'
          animate='show'
          custom={3}
          className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl overflow-hidden shadow-surface'>
          <header className='px-5 py-3.5 border-b border-neutral-border bg-gov-cream dark:bg-surface-sunken'>
            <div className='flex items-center gap-2'>
              <PlayCircle className='w-4 h-4 text-gov-sage' />
              <h2 className='font-display text-lg text-neutral-text'>Sources</h2>
            </div>
          </header>
          {schedule.isLoading ? (
            <div className='py-16 flex justify-center'>
              <Loader2 className='w-5 h-5 text-gov-sage animate-spin' />
            </div>
          ) : !schedule.data ? (
            <div className='py-12 px-6 text-center text-gov-copper dark:text-red-400 text-sm'>
              <AlertTriangle className='w-6 h-6 mx-auto mb-2' />
              Could not load schedule.
            </div>
          ) : (
            <ul className='divide-y divide-neutral-border/60'>
              {Object.entries(schedule.data.sources).map(([source, decision], i) => (
                <SourceRow
                  key={source}
                  index={i}
                  source={source}
                  decision={decision}
                  pending={trigger.isPending && trigger.variables?.source === source}
                  onTrigger={(dryRun) => trigger.mutate({ source, dryRun })}
                />
              ))}
            </ul>
          )}
        </motion.section>
      </div>
    </PageShell>
  );
}

function SummaryCard({
  icon: Icon,
  label,
  value,
  valueClassName = '',
  small = false,
  order = 0,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  valueClassName?: string;
  small?: boolean;
  order?: number;
}) {
  return (
    <motion.div
      variants={fadeUp}
      initial='hidden'
      animate='show'
      custom={order}
      className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl p-5 shadow-surface'>
      <div className='flex items-center gap-2 mb-2'>
        <div className='w-7 h-7 rounded-lg bg-gov-sage/15 border border-gov-sage/20 flex items-center justify-center'>
          <Icon className='w-3.5 h-3.5 text-gov-sage' />
        </div>
        <p className='text-[10px] uppercase tracking-wider text-neutral-muted font-semibold'>
          {label}
        </p>
      </div>
      <p
        className={`${
          small ? 'text-sm font-medium text-neutral-text mt-2' : 'text-2xl font-bold text-neutral-text font-display'
        } ${valueClassName}`}>
        {value}
      </p>
    </motion.div>
  );
}

function SourceRow({
  source,
  decision,
  pending,
  onTrigger,
  index,
}: {
  source: string;
  decision: ScheduleSourceDecision;
  pending: boolean;
  onTrigger: (dryRun: boolean) => void;
  index: number;
}) {
  const [confirming, setConfirming] = useState<null | 'real' | 'dry'>(null);
  const Icon = decision.should_run ? CheckCircle2 : Clock;
  const colour = decision.should_run ? 'text-emerald-600 dark:text-emerald-400' : 'text-neutral-muted/40';

  return (
    <motion.li
      variants={fadeUp}
      initial='hidden'
      animate='show'
      custom={index}
      className='px-5 py-4 flex flex-wrap items-center gap-4 hover:bg-gov-cream/40 dark:hover:bg-surface-elevated transition-colors'>
      <div className='flex items-center gap-3 min-w-[12rem]'>
        <Icon className={`w-5 h-5 ${colour}`} />
        <div>
          <p className='font-mono text-sm font-semibold text-neutral-text'>{source}</p>
          {decision.current_period && (
            <p className='text-[10px] uppercase tracking-wider text-neutral-muted mt-0.5'>
              {decision.current_period}
            </p>
          )}
        </div>
      </div>

      <div className='flex-1 min-w-[16rem] text-xs text-neutral-muted'>
        <p>
          <span className='text-neutral-muted/70 mr-1'>Reason:</span>
          {decision.reason}
        </p>
        {decision.next_run && (
          <p className='mt-0.5'>
            <span className='text-neutral-muted/70 mr-1'>Next run:</span>
            {new Date(decision.next_run).toLocaleString()}
            {decision.next_reason ? ` · ${decision.next_reason}` : ''}
          </p>
        )}
      </div>

      <div className='flex items-center gap-2 ml-auto'>
        {confirming ? (
          <div className='flex items-center gap-2'>
            <span className='text-xs text-neutral-muted'>
              Run {source} {confirming === 'dry' ? '(dry-run)' : 'now'}?
            </span>
            <button
              disabled={pending}
              onClick={() => {
                onTrigger(confirming === 'dry');
                setConfirming(null);
              }}
              className='px-3 py-1.5 bg-gov-sage text-white text-xs font-semibold rounded-full hover:bg-gov-sage/90 disabled:opacity-50 shadow-surface'>
              {pending ? <Loader2 className='w-3 h-3 animate-spin' /> : 'Confirm'}
            </button>
            <button
              onClick={() => setConfirming(null)}
              className='px-2 py-1 text-xs text-neutral-muted hover:text-neutral-text'>
              Cancel
            </button>
          </div>
        ) : (
          <>
            <button
              onClick={() => setConfirming('dry')}
              className='inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-full bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text transition-all shadow-surface'>
              Dry-run
            </button>
            <button
              onClick={() => setConfirming('real')}
              className='inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-full bg-gov-forest text-white hover:bg-gov-dark transition-colors shadow-surface'>
              <PlayCircle className='w-3 h-3' />
              Trigger
            </button>
          </>
        )}
      </div>
    </motion.li>
  );
}
