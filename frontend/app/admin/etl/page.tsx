/**
 * /admin/etl — ETL schedule + manual trigger.
 *
 * Shows a calendar plan and explicit availability of execution evidence.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  RefreshCcw,
  Zap,
} from 'lucide-react';
import {parseSchedule,parseEtlHealth,type ScheduleSourceDecision} from '@/lib/admin/etl';
import {useOperationsAccess} from '@/lib/admin/ingestionPolling';

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function AdminEtlPage() {
  const access = useOperationsAccess(['etl-schedule','etl-health']);

  const schedule = useQuery({
    queryKey: ['admin', 'etl-schedule', access.actorId],
    queryFn: async ({ signal }) => parseSchedule((await api.get('/admin/etl/schedule', { signal })).data),
    enabled: access.enabled,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });

  const health = useQuery({
    queryKey: ['admin', 'etl-health', access.actorId],
    queryFn: async ({ signal }) => parseEtlHealth((await api.get('/admin/etl/health', { signal })).data),
    enabled: access.enabled,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });

  const planData = access.isAdmin && !schedule.isError ? schedule.data : undefined;
  const healthData = access.isAdmin && !health.isError ? health.data : undefined;
  if (!access.isAdmin) return <PageShell title='ETL Schedule'><p>{access.isLoading ? 'Verifying access…' : 'Admin access required.'}</p></PageShell>;

  return (
    <PageShell
      title='ETL Schedule'
      subtitle='Calendar planning for source checks. Execution requires the dedicated runner.'
      back={{ href: '/admin', label: 'Back to overview' }}>
      <div className='space-y-5'>
        <p className='text-sm text-neutral-muted'>A calendar calculation does not establish scheduler activity, job execution or financial data freshness.</p>
        <p role='status' className='text-sm text-neutral-muted'>{healthData?.manual_trigger.reason ?? 'Manual execution is unavailable. No job was accepted.'}</p>
        {health.isError && <p role='alert' className='text-sm text-gov-copper'>Could not load execution evidence.</p>}
        {schedule.isError && <p role='alert' className='text-sm text-gov-copper'>Calendar plan unavailable. Refresh to retry.</p>}
        <div className='flex items-center justify-end'>
          <button
            disabled={schedule.isFetching || health.isFetching || !access.enabled}
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
            label='Planned today'
            value={
              planData
                ? `${planData.summary.sources_running_today}/${planData.summary.total_sources}`
                : '…'
            }
          />
          <SummaryCard
            order={1}
            icon={Activity}
            label='Worker evidence'
            value={healthData ? healthData.worker_status : '…'}
            valueClassName='capitalize'
          />
          <SummaryCard
            order={2}
            icon={Zap}
            label='Planning vs fixed'
            value={planData?.summary.efficiency_vs_fixed_schedule ?? '—'}
            small
          />
        </div>

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
          ) : !planData ? (
            <div className='py-12 px-6 text-center text-gov-copper dark:text-red-400 text-sm'>
              <AlertTriangle className='w-6 h-6 mx-auto mb-2' />
              Could not load schedule.
            </div>
          ) : (
            <ul className='divide-y divide-neutral-border/60'>
              {Object.entries(planData.sources).map(([source, decision], i) => (
                <SourceRow
                  key={source}
                  index={i}
                  source={source}
                  decision={decision}

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
        <p className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold'>
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
  index,
}: {
  source: string;
  decision: ScheduleSourceDecision;
  index: number;
}) {
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
            <p className='text-[11px] uppercase tracking-wider text-neutral-muted mt-0.5'>
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
            <span className='text-neutral-muted/70 mr-1'>Next planned check:</span>
            {new Date(decision.next_run).toLocaleString()}
            {decision.next_reason ? ` · ${decision.next_reason}` : ''}
          </p>
        )}
      </div>

      <div className='flex flex-wrap items-center gap-2 ml-auto'>
        <button disabled title='Dedicated worker dispatch unavailable' className='px-3 py-1.5 text-xs font-semibold rounded-full border border-neutral-border text-neutral-muted disabled:opacity-50'>Dry-run</button>
        <button disabled title='Dedicated worker dispatch unavailable' className='px-3 py-1.5 text-xs font-semibold rounded-full bg-gov-forest text-white disabled:opacity-50'>Trigger</button>
      </div>
    </motion.li>
  );
}
