'use client';

import PageShell from '@/components/layout/PageShell';
import type { FindingsFilters, WorstCounty } from '@/lib/api/audits';
import {
  useAuditDashboardSummary,
  useAuditFindings,
  useAuditTrends,
  useRecurringFindings,
} from '@/lib/react-query';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowUpDown,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileWarning,
  Loader2,
  Search,
  Shield,
  TrendingUp,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/* ═══════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════ */

function fmtKES(val: number): string {
  if (!val || val === 0) return 'KES 0';
  const abs = Math.abs(val);
  if (abs >= 1e12) return `KES ${(val / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(val / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `KES ${(val / 1e6).toFixed(1)}M`;
  return `KES ${val.toLocaleString()}`;
}

function fmtShort(val: number): string {
  if (!val || val === 0) return '0';
  const abs = Math.abs(val);
  if (abs >= 1e12) return `${(val / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `${(val / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(val / 1e6).toFixed(0)}M`;
  return val.toLocaleString();
}

const TYPE_COLORS: Record<string, string> = {
  'Financial Irregularity': '#ef4444',
  'Compliance Issue': '#f59e0b',
  'Asset Management': '#8b5cf6',
  'Revenue Collection': '#3b82f6',
  'Procurement': '#ec4899',
  'Internal Controls': '#14b8a6',
  'Pending Bills': '#f97316',
  'Human Resource': '#6366f1',
};

const OPINION_COLORS: Record<string, string> = {
  Adverse: '#ef4444',
  Disclaimer: '#f59e0b',
  Qualified: '#f97316',
  Unqualified: '#22c55e',
};

function getTypeColor(type: string): string {
  return TYPE_COLORS[type] || '#94a3b8';
}

/* ═══════════════════════════════════════════════════════
   Section animation wrapper
   ═══════════════════════════════════════════════════════ */

function Section({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, delay }}
      className={className}>
      {children}
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════
   Page Component
   ═══════════════════════════════════════════════════════ */

export default function AuditFindingsPage() {
  // --- Filters state ---
  const [filters, setFilters] = useState<FindingsFilters>({ page: 1, limit: 20 });
  const [worstSort, setWorstSort] = useState<'amount' | 'count'>('amount');

  // --- Data hooks ---
  const { data: summary, isLoading: summaryLoading } = useAuditDashboardSummary();
  const { data: trends, isLoading: trendsLoading } = useAuditTrends();
  const { data: recurring, isLoading: recurringLoading } = useRecurringFindings();
  const { data: findings, isLoading: findingsLoading } = useAuditFindings(filters);

  // --- Derived data ---
  const typeChartData = useMemo(() => {
    if (!summary?.findings_by_type) return [];
    return Object.entries(summary.findings_by_type)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [summary]);

  const trendsChartData = useMemo(() => {
    if (!trends) return [];
    return trends.years.map((year) => ({
      year: String(year),
      findings: trends.findings_per_year[String(year)] || 0,
      amount: (trends.amount_per_year[String(year)] || 0) / 1e9,
    }));
  }, [trends]);

  const worstCounties = useMemo(() => {
    if (!summary?.worst_counties) return [];
    const sorted = [...summary.worst_counties];
    if (worstSort === 'count') {
      sorted.sort((a, b) => b.finding_count - a.finding_count);
    }
    return sorted;
  }, [summary, worstSort]);

  const adverseCount = useMemo(() => {
    if (!summary?.findings_by_opinion) return 0;
    return (summary.findings_by_opinion['Adverse'] || 0) + (summary.findings_by_opinion['Disclaimer'] || 0);
  }, [summary]);

  // --- Filter options ---
  const yearOptions = useMemo(() => {
    if (!summary?.year_range?.min_year || !summary?.year_range?.max_year) return [];
    const years = [];
    for (let y = summary.year_range.max_year; y >= summary.year_range.min_year; y--) {
      years.push(y);
    }
    return years;
  }, [summary]);

  const typeOptions = useMemo(() => {
    if (!summary?.findings_by_type) return [];
    return Object.keys(summary.findings_by_type).sort();
  }, [summary]);

  const opinionOptions = useMemo(() => {
    if (!summary?.findings_by_opinion) return [];
    return Object.keys(summary.findings_by_opinion).sort();
  }, [summary]);

  // --- Filter handlers ---
  const updateFilter = useCallback((key: keyof FindingsFilters, value: any) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value || undefined,
      page: key === 'page' ? value : 1,
    }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({ page: 1, limit: 20 });
  }, []);

  const hasActiveFilters = !!(filters.county_id || filters.year || filters.query_type || filters.severity || filters.audit_opinion || filters.status);

  const totalPages = findings ? Math.ceil(findings.total / (filters.limit || 20)) : 0;

  // --- Loading state ---
  if (summaryLoading) {
    return (
      <PageShell title='Audit Findings' subtitle='National audit findings dashboard'>
        <div className='flex items-center justify-center py-32'>
          <Loader2 className='w-8 h-8 animate-spin text-gov-sage' />
          <span className='ml-3 text-gov-dark/60 font-medium'>Loading audit data...</span>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title='Audit Findings'
      subtitle='Tracking how public money is spent and where it goes missing'>
      {/* ═══ A. HERO STATS ═══ */}
      <Section>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4'>
          <StatCard
            label='Irregular Expenditure'
            value={fmtKES(summary?.total_irregular_expenditure || 0)}
            icon={<AlertTriangle className='w-5 h-5' />}
            color='red'
          />
          <StatCard
            label='Unsupported Expenditure'
            value={fmtKES(summary?.total_unsupported_expenditure || 0)}
            icon={<FileWarning className='w-5 h-5' />}
            color='amber'
          />
          <StatCard
            label='Total Findings'
            value={(summary?.total_findings || 0).toLocaleString()}
            icon={<Search className='w-5 h-5' />}
            color='blue'
          />
          <StatCard
            label='Adverse/Disclaimer Opinions'
            value={adverseCount.toLocaleString()}
            icon={<Shield className='w-5 h-5' />}
            color='red'
            subtitle='Counties with worst opinions'
          />
        </div>
      </Section>

      {/* ═══ B. WORST OFFENDERS ═══ */}
      <Section delay={0.1}>
        <div className='space-y-3'>
          <div className='flex items-center justify-between'>
            <h2 className='font-display text-xl text-gov-dark'>Top 10 Worst Offenders</h2>
            <div className='flex items-center gap-2'>
              <span className='text-xs text-gov-dark/50'>Sort by:</span>
              <button
                onClick={() => setWorstSort('amount')}
                className={`text-xs px-3 py-1 rounded-full transition-colors ${
                  worstSort === 'amount'
                    ? 'bg-gov-forest text-white'
                    : 'bg-gov-dark/5 text-gov-dark/60 hover:bg-gov-dark/10'
                }`}>
                Amount
              </button>
              <button
                onClick={() => setWorstSort('count')}
                className={`text-xs px-3 py-1 rounded-full transition-colors ${
                  worstSort === 'count'
                    ? 'bg-gov-forest text-white'
                    : 'bg-gov-dark/5 text-gov-dark/60 hover:bg-gov-dark/10'
                }`}>
                Findings
              </button>
            </div>
          </div>

          <div className='overflow-x-auto'>
            <table className='w-full text-sm'>
              <thead>
                <tr className='border-b border-gov-dark/10 text-left'>
                  <th className='py-2 pr-3 font-semibold text-gov-dark/70 w-8'>#</th>
                  <th className='py-2 pr-3 font-semibold text-gov-dark/70'>County</th>
                  <th className='py-2 pr-3 font-semibold text-gov-dark/70 text-right'>Flagged Amount</th>
                  <th className='py-2 font-semibold text-gov-dark/70 text-right'>Findings</th>
                </tr>
              </thead>
              <tbody>
                {worstCounties.map((c, i) => (
                  <tr
                    key={c.county_id}
                    className='border-b border-gov-dark/5 hover:bg-gov-forest/[0.03] transition-colors group'>
                    <td className='py-2.5 pr-3 text-gov-dark/40 font-mono text-xs'>{i + 1}</td>
                    <td className='py-2.5 pr-3'>
                      <Link
                        href={`/counties/${c.county_id}`}
                        className='text-gov-forest font-medium hover:underline group-hover:text-gov-sage transition-colors'>
                        {c.county_name}
                      </Link>
                    </td>
                    <td className='py-2.5 pr-3 text-right font-mono text-red-600'>
                      {fmtKES(c.total_amount)}
                    </td>
                    <td className='py-2.5 text-right font-mono'>{c.finding_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Section>

      {/* ═══ C. FINDINGS BY TYPE + D. TRENDS — side by side ═══ */}
      <Section delay={0.15}>
        <div className='grid grid-cols-1 lg:grid-cols-2 gap-6'>
          {/* C. Findings by Type */}
          <div className='space-y-3'>
            <h2 className='font-display text-xl text-gov-dark'>Findings by Type</h2>
            {typeChartData.length > 0 ? (
              <div className='h-[320px]'>
                <ResponsiveContainer width='100%' height='100%'>
                  <BarChart data={typeChartData} layout='vertical' margin={{ left: 0, right: 16 }}>
                    <CartesianGrid strokeDasharray='3 3' stroke='#e5e7eb' horizontal={false} />
                    <XAxis type='number' tick={{ fontSize: 11 }} />
                    <YAxis
                      type='category'
                      dataKey='name'
                      width={130}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#fff',
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(val: number) => [val.toLocaleString(), 'Findings']}
                    />
                    <Bar dataKey='value' radius={[0, 4, 4, 0]}>
                      {typeChartData.map((entry) => (
                        <Cell key={entry.name} fill={getTypeColor(entry.name)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className='h-[320px] flex items-center justify-center text-gov-dark/40'>
                No data available
              </div>
            )}
          </div>

          {/* D. Year-on-Year Trends */}
          <div className='space-y-3'>
            <h2 className='font-display text-xl text-gov-dark'>Year-on-Year Trends</h2>
            {trendsLoading ? (
              <div className='h-[320px] flex items-center justify-center'>
                <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
              </div>
            ) : trendsChartData.length > 0 ? (
              <div className='h-[320px]'>
                <ResponsiveContainer width='100%' height='100%'>
                  <LineChart data={trendsChartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray='3 3' stroke='#e5e7eb' />
                    <XAxis dataKey='year' tick={{ fontSize: 11 }} />
                    <YAxis
                      yAxisId='left'
                      tick={{ fontSize: 11 }}
                      label={{
                        value: 'Findings',
                        angle: -90,
                        position: 'insideLeft',
                        style: { fontSize: 11, fill: '#6b7280' },
                      }}
                    />
                    <YAxis
                      yAxisId='right'
                      orientation='right'
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v) => `${v}B`}
                      label={{
                        value: 'Amount (KES B)',
                        angle: 90,
                        position: 'insideRight',
                        style: { fontSize: 11, fill: '#6b7280' },
                      }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#fff',
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(val: number, name: string) => {
                        if (name === 'amount') return [`KES ${val.toFixed(1)}B`, 'Total Amount'];
                        return [val.toLocaleString(), 'Findings Count'];
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      yAxisId='left'
                      type='monotone'
                      dataKey='findings'
                      name='Findings Count'
                      stroke='#3b82f6'
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                    <Line
                      yAxisId='right'
                      type='monotone'
                      dataKey='amount'
                      name='Total Amount'
                      stroke='#ef4444'
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                      strokeDasharray='5 5'
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className='h-[320px] flex items-center justify-center text-gov-dark/40'>
                No trend data available
              </div>
            )}
          </div>
        </div>
      </Section>

      {/* ═══ E. RECURRING FINDINGS ═══ */}
      <Section delay={0.2}>
        <div className='space-y-3'>
          <div className='flex items-center gap-3'>
            <h2 className='font-display text-xl text-gov-dark'>Recurring Findings</h2>
            {recurring && (
              <span className='text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-medium'>
                {recurring.total} patterns
              </span>
            )}
          </div>
          <p className='text-sm text-gov-dark/50'>
            Counties with the same type of finding across multiple audit years — the real scandals.
          </p>

          {recurringLoading ? (
            <div className='flex items-center justify-center py-12'>
              <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
            </div>
          ) : recurring && recurring.recurring_findings.length > 0 ? (
            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='border-b border-gov-dark/10 text-left'>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>County</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>Finding Type</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>Years</th>
                    <th className='py-2 font-semibold text-gov-dark/70 text-right'>Total Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {recurring.recurring_findings.slice(0, 20).map((r, i) => (
                    <tr
                      key={`${r.county_name}-${r.query_type}-${i}`}
                      className={`border-b border-gov-dark/5 transition-colors ${
                        r.years_appeared.length >= 3
                          ? 'bg-red-50/50 hover:bg-red-50'
                          : 'hover:bg-gov-forest/[0.03]'
                      }`}>
                      <td className='py-2.5 pr-3 font-medium text-gov-dark'>{r.county_name}</td>
                      <td className='py-2.5 pr-3'>
                        <span
                          className='inline-block px-2 py-0.5 rounded text-xs font-medium text-white'
                          style={{ backgroundColor: getTypeColor(r.query_type) }}>
                          {r.query_type}
                        </span>
                      </td>
                      <td className='py-2.5 pr-3'>
                        <div className='flex flex-wrap gap-1'>
                          {r.years_appeared.map((y) => (
                            <span
                              key={y}
                              className='text-xs px-1.5 py-0.5 rounded bg-gov-dark/5 text-gov-dark/70 font-mono'>
                              {y}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className='py-2.5 text-right font-mono text-red-600'>
                        {r.total_amount > 0 ? fmtKES(r.total_amount) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className='text-center py-8 text-gov-dark/40'>No recurring findings detected</div>
          )}
        </div>
      </Section>

      {/* ═══ F. FILTER BAR ═══ */}
      <Section delay={0.25}>
        <div className='space-y-3'>
          <div className='flex items-center justify-between'>
            <h2 className='font-display text-xl text-gov-dark'>All Findings</h2>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className='flex items-center gap-1 text-xs text-gov-sage hover:text-gov-forest transition-colors'>
                <X className='w-3 h-3' />
                Clear filters
              </button>
            )}
          </div>

          <div className='flex flex-wrap gap-3'>
            {/* Year filter */}
            <FilterSelect
              label='Year'
              value={filters.year?.toString() || ''}
              onChange={(v) => updateFilter('year', v ? parseInt(v) : undefined)}
              options={yearOptions.map((y) => ({ value: String(y), label: String(y) }))}
            />

            {/* Type filter */}
            <FilterSelect
              label='Finding Type'
              value={filters.query_type || ''}
              onChange={(v) => updateFilter('query_type', v || undefined)}
              options={typeOptions.map((t) => ({ value: t, label: t }))}
            />

            {/* Opinion filter */}
            <FilterSelect
              label='Audit Opinion'
              value={filters.audit_opinion || ''}
              onChange={(v) => updateFilter('audit_opinion', v || undefined)}
              options={opinionOptions.map((o) => ({ value: o, label: o }))}
            />

            {/* Severity filter */}
            <FilterSelect
              label='Severity'
              value={filters.severity || ''}
              onChange={(v) => updateFilter('severity', v || undefined)}
              options={[
                { value: 'Critical', label: 'Critical' },
                { value: 'High', label: 'High' },
                { value: 'Medium', label: 'Medium' },
                { value: 'Low', label: 'Low' },
              ]}
            />

            {/* Status filter */}
            <FilterSelect
              label='Status'
              value={filters.status || ''}
              onChange={(v) => updateFilter('status', v || undefined)}
              options={[
                { value: 'Unresolved', label: 'Unresolved' },
                { value: 'Resolved', label: 'Resolved' },
                { value: 'Partially Resolved', label: 'Partially Resolved' },
              ]}
            />
          </div>
        </div>
      </Section>

      {/* ═══ G. FINDINGS TABLE ═══ */}
      <Section delay={0.3}>
        {findingsLoading ? (
          <div className='flex items-center justify-center py-16'>
            <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
            <span className='ml-3 text-gov-dark/60'>Loading findings...</span>
          </div>
        ) : findings && findings.items.length > 0 ? (
          <div className='space-y-4'>
            <div className='text-xs text-gov-dark/50'>
              Showing {(findings.page - 1) * (filters.limit || 20) + 1}–
              {Math.min(findings.page * (filters.limit || 20), findings.total)} of{' '}
              {findings.total.toLocaleString()} findings
            </div>

            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='border-b border-gov-dark/10 text-left'>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>County</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>Year</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>Type</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 text-right'>Amount</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>Severity</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70'>Status</th>
                    <th className='py-2 font-semibold text-gov-dark/70'>Opinion</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.items.map((f) => (
                    <tr
                      key={f.id}
                      className='border-b border-gov-dark/5 hover:bg-gov-forest/[0.03] transition-colors'
                      title={f.finding_text}>
                      <td className='py-2.5 pr-3'>
                        <Link
                          href={`/counties/${f.entity_id}`}
                          className='text-gov-forest font-medium hover:underline'>
                          {f.county_name || `County ${f.entity_id}`}
                        </Link>
                      </td>
                      <td className='py-2.5 pr-3 font-mono text-xs'>{f.audit_year || '—'}</td>
                      <td className='py-2.5 pr-3'>
                        {f.query_type ? (
                          <span
                            className='inline-block px-2 py-0.5 rounded text-xs font-medium text-white'
                            style={{ backgroundColor: getTypeColor(f.query_type) }}>
                            {f.query_type}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className='py-2.5 pr-3 text-right font-mono text-red-600'>
                        {f.amount ? fmtKES(f.amount) : '—'}
                      </td>
                      <td className='py-2.5 pr-3'>
                        <SeverityBadge severity={f.severity} />
                      </td>
                      <td className='py-2.5 pr-3'>
                        <StatusBadge status={f.status} />
                      </td>
                      <td className='py-2.5'>
                        {f.audit_opinion ? (
                          <span
                            className='text-xs font-medium'
                            style={{ color: OPINION_COLORS[f.audit_opinion] || '#6b7280' }}>
                            {f.audit_opinion}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className='flex items-center justify-between pt-2'>
                <button
                  onClick={() => updateFilter('page', Math.max(1, (filters.page || 1) - 1))}
                  disabled={(filters.page || 1) <= 1}
                  className='flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-gov-dark/5 hover:bg-gov-dark/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors'>
                  <ChevronLeft className='w-4 h-4' />
                  Previous
                </button>
                <span className='text-xs text-gov-dark/60'>
                  Page {filters.page || 1} of {totalPages}
                </span>
                <button
                  onClick={() => updateFilter('page', Math.min(totalPages, (filters.page || 1) + 1))}
                  disabled={(filters.page || 1) >= totalPages}
                  className='flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-gov-dark/5 hover:bg-gov-dark/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors'>
                  Next
                  <ChevronRight className='w-4 h-4' />
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className='text-center py-16 text-gov-dark/40'>
            {hasActiveFilters ? 'No findings match your filters.' : 'No findings data available.'}
          </div>
        )}
      </Section>
    </PageShell>
  );
}

/* ═══════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════ */

function StatCard({
  label,
  value,
  icon,
  color,
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: 'red' | 'amber' | 'blue' | 'green';
  subtitle?: string;
}) {
  const colorMap = {
    red: 'bg-red-50 text-red-600 border-red-200/50',
    amber: 'bg-amber-50 text-amber-600 border-amber-200/50',
    blue: 'bg-blue-50 text-blue-600 border-blue-200/50',
    green: 'bg-emerald-50 text-emerald-600 border-emerald-200/50',
  };
  const iconBg = {
    red: 'bg-red-100 text-red-500',
    amber: 'bg-amber-100 text-amber-500',
    blue: 'bg-blue-100 text-blue-500',
    green: 'bg-emerald-100 text-emerald-500',
  };

  return (
    <div className={`rounded-xl p-4 border ${colorMap[color]} transition-shadow hover:shadow-md`}>
      <div className='flex items-start justify-between mb-2'>
        <span className='text-xs font-medium uppercase tracking-wider opacity-70'>{label}</span>
        <div className={`p-1.5 rounded-lg ${iconBg[color]}`}>{icon}</div>
      </div>
      <div className='font-display text-2xl font-bold tracking-tight'>{value}</div>
      {subtitle && <p className='text-xs mt-1 opacity-60'>{subtitle}</p>}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className='flex flex-col gap-1'>
      <label className='text-[10px] font-semibold text-gov-dark/50 uppercase tracking-wider'>
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className='text-sm px-3 py-1.5 rounded-lg bg-white/60 border border-gov-dark/10 text-gov-dark focus:outline-none focus:ring-2 focus:ring-gov-sage/30 focus:border-gov-sage appearance-none pr-8 min-w-[140px]'
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'right 8px center',
        }}>
        <option value=''>All</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    Critical: 'bg-red-100 text-red-700',
    High: 'bg-orange-100 text-orange-700',
    Medium: 'bg-amber-100 text-amber-700',
    Low: 'bg-green-100 text-green-700',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${styles[severity] || 'bg-gray-100 text-gray-600'}`}>
      {severity}
    </span>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className='text-gov-dark/30'>—</span>;
  const styles: Record<string, string> = {
    Resolved: 'bg-emerald-100 text-emerald-700',
    Unresolved: 'bg-red-100 text-red-700',
    'Partially Resolved': 'bg-amber-100 text-amber-700',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${styles[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  );
}
