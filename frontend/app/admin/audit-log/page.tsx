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

  const actor_id = searchParams.get('actor_id') ?? '';
  const action = searchParams.get('action') ?? '';
  const target_type = searchParams.get('target_type') ?? '';
  const target_id = searchParams.get('target_id') ?? '';
  const days = Number(searchParams.get('days') ?? '30');
  const page = Number(searchParams.get('page') ?? '1');

  const setQuery = useCallback(
    (updates: Record<string, string | number | null>) => {
      const next = new URLSearchParams(searchParams);
      for (const [k, v] of Object.entries(updates)) {
        if (v === null || v === '') next.delete(k);
        else next.set(k, String(v));
      }
      if (!('page' in updates)) next.delete('page');
      router.replace(`/admin/audit-log${next.size ? '?' + next.toString() : ''}`);
    },
    [router, searchParams]
  );

  const { data, isLoading, error, refetch, isFetching } = useQuery<AuditList>({
    queryKey: ['admin', 'audit-log', { actor_id, action, target_type, target_id, days, page }],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE, days };
      if (actor_id) params.actor_id = actor_id;
      if (action) params.action = action;
      if (target_type) params.target_type = target_type;
      if (target_id) params.target_id = target_id;
      return (await api.get('/admin/audit-log', { params })).data;
    },
    staleTime: 15_000,
  });

  return (
    <PageShell
      title='Audit Log'
      subtitle={
        data
          ? `${data.total.toLocaleString()} action${data.total === 1 ? '' : 's'} recorded.`
          : 'Every privileged admin action, attributable to its actor.'
      }
      back={{ href: '/admin', label: 'Back to overview' }}>
      <div className='space-y-5'>
        {/* ── Filter bar ── */}
        <div className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl p-4 shadow-surface flex flex-wrap items-end gap-3'>
          <FilterField label='Actor (UUID)'>
            <input
              type='text'
              value={actor_id}
              onChange={(e) => setQuery({ actor_id: e.target.value || null })}
              placeholder='admin user id'
              className='w-56 px-3 py-1.5 text-xs rounded-lg border border-neutral-border focus:outline-none focus:ring-2 focus:ring-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken font-mono'
            />
          </FilterField>
          <FilterField label='Action'>
            <input
              type='text'
              value={action}
              onChange={(e) => setQuery({ action: e.target.value || null })}
              placeholder='e.g. users.update_roles'
              className='w-56 px-3 py-1.5 text-xs rounded-lg border border-neutral-border focus:outline-none focus:ring-2 focus:ring-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken font-mono'
            />
          </FilterField>
          <FilterField label='Target type'>
            <input
              type='text'
              value={target_type}
              onChange={(e) => setQuery({ target_type: e.target.value || null })}
              placeholder='user / etl_source'
              className='w-44 px-3 py-1.5 text-xs rounded-lg border border-neutral-border focus:outline-none focus:ring-2 focus:ring-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken font-mono'
            />
          </FilterField>
          <FilterField label='Time window'>
            <select
              value={days}
              onChange={(e) => setQuery({ days: e.target.value })}
              className='w-36 px-3 py-1.5 text-sm rounded-lg border border-neutral-border focus:outline-none focus:ring-2 focus:ring-gov-sage/40 bg-gov-cream/40 dark:bg-surface-sunken'>
              {DAYS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.value === 0 ? opt.label : `Last ${opt.label}`}
                </option>
              ))}
            </select>
          </FilterField>
          <div className='ml-auto flex items-center gap-2'>
            {(actor_id || action || target_type || target_id || days !== 30) && (
              <button
                onClick={() => router.replace('/admin/audit-log')}
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

        {isLoading ? (
          <BodyState>
            <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
            <p className='text-neutral-muted text-sm'>Loading audit log…</p>
          </BodyState>
        ) : error ? (
          <BodyState>
            <XCircle className='w-8 h-8 text-gov-copper dark:text-red-400' />
            <p className='text-gov-copper dark:text-red-400 text-sm'>Could not load audit log.</p>
          </BodyState>
        ) : !data || data.entries.length === 0 ? (
          <BodyState>
            <Pause className='w-8 h-8 text-neutral-muted/40' />
            <p className='text-neutral-muted text-sm'>No actions match these filters.</p>
          </BodyState>
        ) : (
          <>
            <ul className='space-y-2'>
              {data.entries.map((entry, i) => (
                <AuditRow key={entry.id} entry={entry} index={i} />
              ))}
            </ul>
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
        <span className='text-xs text-neutral-muted ml-auto whitespace-nowrap'>
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
        <div className='px-4 pb-4 border-t border-neutral-border'>
          <p className='text-[10px] uppercase tracking-wider text-neutral-muted font-semibold mt-3 mb-1.5'>
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

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
