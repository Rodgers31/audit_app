/**
 * National Missing Funds Tracker
 *
 * Rolls up every "missing funds" case flagged in audits across all 47
 * counties into a single page. Answers: how much public money is
 * unaccounted for right now, which counties have the biggest losses,
 * and what's the status of each case?
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, Clock, Loader2, Search, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

interface MissingCase {
  case_id: string | null;
  county: string;
  county_id?: string | null;
  amount: number;
  amount_label: string | null;
  period: string | null;
  status: string;
  description: string;
}

interface MissingFundsResponse {
  total_amount: number;
  total_cases: number;
  affected_counties: number;
  by_status: Record<string, number>;
  top_counties: Array<{ county: string; cases: number; amount: number }>;
  cases: MissingCase[];
}

function fmtKES(n: number): string {
  if (n >= 1e9) return `KES ${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `KES ${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}

const STATUS_STYLE: Record<
  string,
  { label: string; icon: typeof AlertTriangle; bg: string; text: string; border: string }
> = {
  active_investigation: {
    label: 'Active Investigation',
    icon: AlertTriangle,
    bg: 'bg-rose-50',
    text: 'text-rose-800',
    border: 'border-rose-200',
  },
  recovery_ongoing: {
    label: 'Recovery Ongoing',
    icon: Clock,
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    border: 'border-amber-200',
  },
  resolved: {
    label: 'Resolved',
    icon: CheckCircle2,
    bg: 'bg-emerald-50',
    text: 'text-emerald-800',
    border: 'border-emerald-200',
  },
  unknown: {
    label: 'Unknown',
    icon: Clock,
    bg: 'bg-gray-50 dark:bg-surface-elevated',
    text: 'text-gray-700 dark:text-neutral-muted',
    border: 'border-gray-200 dark:border-neutral-border',
  },
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[status] || STATUS_STYLE.unknown;
  const Icon = style.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded-full border ${style.bg} ${style.text} ${style.border}`}>
      <Icon size={11} />
      {style.label}
    </span>
  );
}

export default function MissingFundsPage() {
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const { data, isLoading, error } = useQuery<MissingFundsResponse>({
    queryKey: ['accountability', 'missing-funds'],
    queryFn: async () =>
      (await api.get<MissingFundsResponse>('/accountability/missing-funds')).data,
    staleTime: 10 * 60 * 1000,
  });

  const filtered = useMemo(() => {
    const cases = data?.cases || [];
    const q = query.toLowerCase().trim();
    return cases.filter((c) => {
      if (statusFilter !== 'all' && c.status !== statusFilter) return false;
      if (!q) return true;
      return (
        c.county.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        (c.period || '').toLowerCase().includes(q)
      );
    });
  }, [data, query, statusFilter]);

  const statuses = Object.keys(data?.by_status || {});

  return (
    <PageShell
      title='Missing Funds Tracker'
      subtitle='Public money that the Office of the Auditor-General has flagged as unaccounted for, across every county government. Updated as new audit reports are released.'
      back={{ href: '/', label: 'Home' }}>
      <div className='space-y-6'>
        {/* Top-line stats */}
        <div className='grid grid-cols-1 sm:grid-cols-3 gap-4'>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              Total flagged
            </div>
            <div className='text-3xl font-bold text-rose-700 tabular-nums'>
              {fmtKES(data?.total_amount || 0)}
            </div>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-1'>
              Across {data?.total_cases || 0} documented cases
            </div>
          </div>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              Counties affected
            </div>
            <div className='text-3xl font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
              {data?.affected_counties || 0}
              <span className='text-base text-gray-400 dark:text-neutral-muted/80 font-normal'> / 47</span>
            </div>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-1'>With at least one flagged case</div>
          </div>
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold mb-1'>
              Recovery status
            </div>
            <div className='flex flex-wrap gap-2 mt-2'>
              {Object.entries(data?.by_status || {}).map(([status, amount]) => (
                <div key={status} className='text-xs'>
                  <StatusBadge status={status} />
                  <div className='text-sm font-bold text-gray-900 dark:text-neutral-text tabular-nums mt-1'>
                    {fmtKES(amount)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Top counties */}
        {data?.top_counties && data.top_counties.length > 0 && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='flex items-center gap-2 mb-3'>
              <TrendingUp size={16} className='text-rose-600' />
              <h2 className='text-sm font-semibold text-gray-800 dark:text-neutral-text'>
                Counties with the largest flagged amounts
              </h2>
            </div>
            <div className='space-y-2'>
              {data.top_counties.map((c, i) => {
                const pct = (c.amount / (data.total_amount || 1)) * 100;
                return (
                  <div key={c.county} className='flex items-center gap-3'>
                    <div className='w-6 text-xs font-bold text-gray-400 dark:text-neutral-muted/80 tabular-nums'>
                      #{i + 1}
                    </div>
                    <div className='w-36 text-sm font-semibold text-gray-800 dark:text-neutral-text truncate'>
                      {c.county}
                    </div>
                    <div className='flex-1 h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                      <div
                        className='h-full bg-gradient-to-r from-rose-400 to-rose-600'
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    <div className='w-28 text-right text-sm font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                      {fmtKES(c.amount)}
                    </div>
                    <div className='w-16 text-right text-xs text-gray-500 dark:text-neutral-muted/80'>
                      {c.cases} case{c.cases === 1 ? '' : 's'}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Search + filters */}
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-4 flex flex-wrap items-center gap-3'>
          <div className='flex-1 min-w-[220px] relative'>
            <Search
              size={14}
              className='absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-muted/80'
            />
            <input
              type='search'
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder='Search by county, description, or period…'
              className='w-full pl-9 pr-3 py-2 text-sm border border-gray-200 dark:border-neutral-border rounded-lg focus:outline-none focus:ring-2 focus:ring-gov-forest/30'
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className='text-sm border border-gray-200 dark:border-neutral-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-gov-forest/30'>
            <option value='all'>All statuses</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {STATUS_STYLE[s]?.label || s}
              </option>
            ))}
          </select>
        </div>

        {/* Case list */}
        {isLoading && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 flex items-center justify-center gap-3 text-gray-500 dark:text-neutral-muted/80'>
            <Loader2 className='animate-spin' size={18} />
            <span>Loading cases…</span>
          </div>
        )}
        {error && (
          <div className='bg-rose-50 border border-rose-200 rounded-xl p-4 text-rose-800 text-sm'>
            Failed to load missing funds. Please refresh.
          </div>
        )}
        {!isLoading && !error && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border divide-y divide-gray-100'>
            {filtered.length === 0 ? (
              <div className='p-8 text-center text-sm text-gray-500 dark:text-neutral-muted/80'>
                No cases match your filter.
              </div>
            ) : (
              filtered.map((c, i) => (
                <div key={`${c.case_id || i}`} className='p-5 hover:bg-gray-50 dark:bg-surface-elevated transition-colors'>
                  <div className='flex items-start justify-between gap-4 flex-wrap'>
                    <div className='min-w-0 flex-1'>
                      <div className='flex items-center gap-2 mb-1.5 flex-wrap'>
                        <Link
                          href={`/counties?search=${encodeURIComponent(c.county)}`}
                          className='text-sm font-bold text-gray-900 dark:text-neutral-text hover:text-gov-forest dark:text-emerald-100 hover:underline'>
                          {c.county}
                        </Link>
                        {c.period && (
                          <span className='text-xs text-gray-500 dark:text-neutral-muted/80'>· {c.period}</span>
                        )}
                        <StatusBadge status={c.status} />
                      </div>
                      <p className='text-sm text-gray-700 dark:text-neutral-muted leading-relaxed'>{c.description}</p>
                      {c.case_id && (
                        <div className='text-[10px] text-gray-400 dark:text-neutral-muted/80 mt-1.5 font-mono'>
                          Case ID: {c.case_id}
                        </div>
                      )}
                    </div>
                    <div className='text-right'>
                      <div className='text-xl font-bold text-rose-700 tabular-nums'>
                        {c.amount_label || fmtKES(c.amount)}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Methodology */}
        <div className='bg-amber-50/60 border border-amber-200 rounded-xl p-5'>
          <div className='flex items-start gap-3'>
            <AlertTriangle className='text-amber-700 mt-0.5 shrink-0' size={18} />
            <div className='text-sm text-gray-700 dark:text-neutral-muted leading-relaxed'>
              <p className='font-semibold text-gray-900 dark:text-neutral-text mb-1'>What counts as &ldquo;missing&rdquo;</p>
              <p>
                Only cases the Office of the Auditor-General has formally flagged as
                unaccounted-for, ineligible expenditure, or unsupported payments are
                listed here. Status labels reflect the most recent public update —
                &ldquo;active investigation&rdquo; means OAG or EACC has an open file.
                Nothing here is an allegation from us; every case traces back to
                a published audit report.
              </p>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
