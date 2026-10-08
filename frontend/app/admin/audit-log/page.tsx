/**
 * /admin/audit-log — paginated, filterable view of admin write actions.
 *
 * Reads /admin/audit-log. Every privileged mutation in the admin
 * API writes a row here via record_admin_action(); this page is the
 * read surface. Filters live in URL query params so links round-trip.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useAdmin } from '@/lib/auth/admin';
import { auditFilters, AuditEntry, AuditList, decodeAudit, timeAgo } from '@/lib/admin/audit';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  ArrowRight,
  Loader2,
  Pause,
  RefreshCcw,
  XCircle,
} from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useState } from 'react';

const PAGE_SIZE = 25;
const DAYS_OPTIONS = [
  { value: 1, label: '24 hours' },
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 0, label: 'All time' },
];

const fadeUp = {
  hidden: { opacity: 0, y: 10 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, delay: i * 0.025, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function AuditLogPage() {
  return (
    <Suspense
      fallback={
        <PageShell title='Audit Log' subtitle='Loading…'>
          <div className='py-16 flex justify-center'>
            <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
          </div>
        </PageShell>
      }>
      <AuditLogInner />
    </Suspense>
  );
}

function AuditLogInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const { isAdmin } = useAdmin();
  const filters = auditFilters(new URLSearchParams(searchParams));
  const { actor_id, action, target_type, target_id, days, page, snapshot_id, as_of, visibility_snapshot } = filters;
  const setQuery = useCallback(
    (updates: Record<string, string | number | null | undefined>) => {
      const next = new URLSearchParams();
      for (const [k, v] of Object.entries({ ...filters, ...updates })) {
        if (v !== null && v !== undefined && v !== '') next.set(k, String(v));
      }
      if (!('page' in updates)) {
        next.delete('page'); next.delete('snapshot_id'); next.delete('as_of'); next.delete('visibility_snapshot');
      }
      router.push(`/admin/audit-log${next.size ? '?' + next.toString() : ''}`, { scroll: false });
    },
    [router, filters]
  );
  const { data, isLoading, error, refetch, isFetching, dataUpdatedAt } = useQuery<AuditList>({
    queryKey: ['admin', 'audit-log', filters],
    queryFn: async ({ signal }) => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE, days };
      for (const [key, value] of Object.entries({ actor_id, action, target_type, target_id })) if (value) params[key] = value;
      if (snapshot_id !== undefined && as_of !== undefined) { params.snapshot_id = snapshot_id; params.as_of = as_of; }
      if (visibility_snapshot !== undefined) params.visibility_snapshot = visibility_snapshot;
      const result = decodeAudit((await api.get('/admin/audit-log', { params, signal, headers: { 'Cache-Control': 'no-store' } })).data);
      if (result.page !== page || result.page_size !== PAGE_SIZE) throw new Error('Unexpected audit page');
      return result;
    },
    enabled: isAdmin, retry: false, gcTime: 0, staleTime: 15_000,
  });

  return (
    <PageShell
      title='Audit Log'
      subtitle={
        data && !error
          ? `${data.total.toLocaleString()} action${data.total === 1 ? '' : 's'} recorded.`
          : 'Recorded user and ETL actions. Social publishing has its own activity trail.'
      }
      back={{ href: '/admin', label: 'Back to overview' }}>
      <div className='space-y-5'>
        <AuditFilters key={searchParams.toString()} filters={filters} apply={setQuery} clear={() => router.push('/admin/audit-log', { scroll: false })} />
        <div className='flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-muted'>
          <p>Audit recording is best-effort. Missing evidence does not prove no activity. Payload fields may be redacted.</p>
          <button onClick={() => { if (page !== 1 || snapshot_id !== undefined) setQuery({ page: 1, snapshot_id: null, as_of: null, visibility_snapshot: null }); else void refetch(); }} disabled={isFetching} className='inline-flex min-h-11 items-center gap-2 px-3 py-1.5 border border-neutral-border rounded-lg focus-visible:ring-2 focus-visible:ring-gov-sage disabled:opacity-50'>
            <RefreshCcw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} aria-hidden='true' />Refresh
          </button>
          {dataUpdatedAt > 0 && <span>{error ? 'Last successful fetch ' : 'Fetched '}{timeAgo(new Date(dataUpdatedAt).toISOString())}{isFetching ? ' · Refreshing…' : ''}</span>}
        </div>

        {isLoading ? (
          <BodyState>
            <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
            <p className='text-neutral-muted text-sm'>Loading audit log…</p>
          </BodyState>
        ) : error ? (
          <BodyState>
            <XCircle className='w-8 h-8 text-gov-copper dark:text-red-400' />
            <p className='text-gov-copper dark:text-red-400 text-sm'>Could not load audit log. Audit evidence is unavailable; retry with Refresh.</p>
          </BodyState>
        ) : !data ? (<BodyState><p>Audit evidence is unavailable.</p></BodyState>) : (
          <>
            {data.entries.length === 0 ? <BodyState>
            <Pause className='w-8 h-8 text-neutral-muted/40' />
            <p className='text-neutral-muted text-sm'>{page > 1 ? 'No entries on this page. Use Prev or refresh the snapshot.' : 'No actions match these filters.'}</p>
          </BodyState> : <ul className='space-y-2'>
              {data.entries.map((entry, i) => (
                <AuditRow key={entry.id} entry={entry} index={i} />
              ))}
            </ul>}
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              hasMore={data.has_more}
              onChange={(p) => setQuery({ page: p, snapshot_id: data.snapshot_id, as_of: data.as_of, visibility_snapshot: data.visibility_snapshot })}
            />
          </>
        )}
      </div>
    </PageShell>
  );
}

function AuditRow({ entry, index }: { entry: AuditEntry; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const hasPayload = entry.payload && Object.keys(entry.payload).length > 0;
  return (
    <motion.li
      variants={fadeUp}
      initial='hidden'
      animate='show'
      custom={index}
      className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl shadow-surface overflow-hidden'>
      <button
        aria-expanded={hasPayload ? expanded : undefined}
        aria-controls={hasPayload ? `audit-payload-${entry.id}` : undefined}
        onClick={() => hasPayload && setExpanded(!expanded)}
        className={`w-full text-left px-4 py-3 flex flex-wrap items-center gap-3 ${
          hasPayload ? 'hover:bg-gov-cream/50 dark:hover:bg-surface-elevated cursor-pointer' : 'cursor-default'
        }`}>
        <span className='inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono font-semibold bg-gov-sage/15 text-gov-forest dark:text-emerald-200 ring-1 ring-inset ring-gov-sage/20'>
          {entry.action}
        </span>
        {entry.target_type && (
          <span className='text-xs text-neutral-muted'>
            <span className='text-neutral-muted/70'>on</span>{' '}
            <span className='font-mono'>{entry.target_type}</span>
            {entry.target_id && (
              <>
                {' / '}
                <span className='font-mono text-neutral-text'>{entry.target_id}</span>
              </>
            )}
          </span>
        )}
        <span className='text-xs text-neutral-muted ml-auto whitespace-nowrap' title={entry.created_at}>
          by{' '}
          <span className='font-medium text-neutral-text'>
            {entry.actor_email
              ? entry.actor_email.split('@')[0]
              : entry.actor_id.slice(0, 8) + '…'}
          </span>{' '}
          · {timeAgo(entry.created_at)}
        </span>
      </button>
      {expanded && hasPayload && (
        <div id={`audit-payload-${entry.id}`} className='px-4 pb-4 border-t border-neutral-border'>
          <p className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold mt-3 mb-1.5'>
            Payload
          </p>
          <pre className='text-xs font-mono bg-gov-cream dark:bg-surface-sunken border border-neutral-border rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all text-neutral-text'>
            {JSON.stringify(entry.payload, null, 2)}
          </pre>
        </div>
      )}
    </motion.li>
  );
}

function AuditFilters({ filters, apply, clear }: { filters: ReturnType<typeof auditFilters>; apply: (updates: Record<string, string | number | null>) => void; clear: () => void }) {
  const [draft, setDraft] = useState(filters);
  return <form onSubmit={event => { event.preventDefault(); apply({ actor_id: draft.actor_id.trim(), action: draft.action.trim(), target_type: draft.target_type.trim(), target_id: draft.target_id.trim(), days: draft.days }); }} className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl p-4 shadow-surface flex flex-wrap items-end gap-3'>
    {([{ key: 'actor_id', label: 'Actor (UUID)', max: 64 }, { key: 'action', label: 'Action', max: 80 }, { key: 'target_type', label: 'Target type', max: 40 }, { key: 'target_id', label: 'Target id', max: 64 }] as const).map(({ key, label, max }) => (
      <label key={key} className='flex flex-col text-xs text-neutral-muted gap-1'>{label}
        <input type='text' value={draft[key]} maxLength={max} onChange={event => setDraft({ ...draft, [key]: event.target.value })} className='w-44 max-w-full min-h-11 px-3 py-1.5 rounded-lg border border-neutral-border focus:ring-2 focus:ring-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken font-mono' />
      </label>
    ))}
    <label className='flex flex-col text-xs text-neutral-muted gap-1'>Time window
      <select value={draft.days} onChange={event => setDraft({ ...draft, days: Number(event.target.value) })} className='min-h-11 px-3 py-1.5 rounded-lg border border-neutral-border bg-gov-cream/40 dark:bg-surface-sunken focus:ring-2 focus:ring-gov-sage/40'>
        {DAYS_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.value === 0 ? opt.label : `Last ${opt.label}`}</option>)}
      </select>
    </label>
    <button type='submit' className='min-h-11 rounded-lg bg-gov-forest text-white px-3 focus-visible:ring-2 focus-visible:ring-gov-gold'>Apply filters</button>
    <button type='button' onClick={clear} className='min-h-11 px-3 underline focus-visible:ring-2 focus-visible:ring-gov-sage'>Clear filters</button>
  </form>;
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
        {total === 0 || start > total ? `Showing 0 entries on this page (${total.toLocaleString()} total)` : `Showing ${start.toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()}`}
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

function BodyState({ children }: { children: React.ReactNode }) {
  return (
    <div className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl py-16 flex flex-col items-center justify-center gap-3 shadow-surface'>
      {children}
    </div>
  );
}
