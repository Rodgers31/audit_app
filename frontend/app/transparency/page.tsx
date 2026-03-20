'use client';

import FollowTheMoney, { YearSelector } from '@/components/FollowTheMoney';
import PageShell from '@/components/layout/PageShell';
import { useCounties } from '@/lib/react-query';
import { useCountyMoneyFlow, useNationalMoneyFlow } from '@/lib/react-query/useMoneyFlow';
import { useAvailableFiscalYears } from '@/lib/react-query';
import { MoneyFlowData } from '@/types';
import { motion } from 'framer-motion';
import {
  ArrowUpDown,
  Loader2,
  Search,
  TrendingDown,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useMemo, useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { getCountyMoneyFlow } from '@/lib/api/moneyFlow';

/* ═══════════ Helpers ═══════════ */

function fmtKES(n: number | null | undefined): string {
  if (n == null || n === 0) return 'KES 0';
  const abs = Math.abs(n);
  if (abs >= 1e12) return `KES ${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `KES ${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}

const DEFAULT_FISCAL_YEARS = ['2024/25', '2023/24', '2022/23', '2021/22', '2020/21'];

type SortKey = 'efficiency' | 'flagged' | 'gap' | 'name';
type SortDir = 'asc' | 'desc';

/* ═══════════ Section Wrapper ═══════════ */

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

/* ═══════════ County Row Data ═══════════ */

interface CountyFlowRow {
  county_id: string;
  county_name: string;
  efficiency_score: number | null;
  flagged_amount: number | null;
  total_gap: number;
  allocated: number | null;
  spent: number | null;
}

/* ═══════════ Page ═══════════ */

export default function TransparencyPage() {
  const [selectedYear, setSelectedYear] = useState(DEFAULT_FISCAL_YEARS[0]);
  const [sortKey, setSortKey] = useState<SortKey>('efficiency');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [searchQuery, setSearchQuery] = useState('');

  const { data: fiscalYears } = useAvailableFiscalYears();
  const { data: nationalFlow, isLoading: nationalLoading } = useNationalMoneyFlow(selectedYear);
  const { data: counties, isLoading: countiesLoading } = useCounties();

  const years = fiscalYears && fiscalYears.length > 0 ? fiscalYears : DEFAULT_FISCAL_YEARS;

  // Fetch money flow for each county
  const countyIds = useMemo(() => (counties || []).map((c) => c.id), [counties]);
  const countyFlowQueries = useQueries({
    queries: countyIds.map((id) => ({
      queryKey: ['counties', id, 'money-flow', selectedYear] as const,
      queryFn: () => getCountyMoneyFlow(id, selectedYear),
      enabled: !!id && !!selectedYear,
      staleTime: 10 * 60 * 1000,
    })),
  });

  const allCountyFlowsLoading = countyFlowQueries.some((q) => q.isLoading);

  // Build comparison table rows
  const countyRows: CountyFlowRow[] = useMemo(() => {
    if (!counties) return [];
    return counties
      .map((county, i) => {
        const flowData = countyFlowQueries[i]?.data as MoneyFlowData | undefined;
        if (!flowData) {
          return {
            county_id: county.id,
            county_name: county.name,
            efficiency_score: null,
            flagged_amount: null,
            total_gap: 0,
            allocated: null,
            spent: null,
          };
        }
        const flaggedStage = flowData.stages.find((s) => s.stage === 'Flagged');
        const allocatedStage = flowData.stages.find((s) => s.stage === 'Allocated');
        const spentStage = flowData.stages.find((s) => s.stage === 'Spent');
        const totalGap = flowData.stages.reduce(
          (sum, s) => sum + (s.gap_from_prev && s.gap_from_prev > 0 ? s.gap_from_prev : 0),
          0
        );
        return {
          county_id: county.id,
          county_name: county.name,
          efficiency_score: flowData.efficiency_score,
          flagged_amount: flaggedStage?.amount || null,
          total_gap: totalGap,
          allocated: allocatedStage?.amount || null,
          spent: spentStage?.amount || null,
        };
      })
      .filter((row) => {
        if (!searchQuery) return true;
        return row.county_name.toLowerCase().includes(searchQuery.toLowerCase());
      });
  }, [counties, countyFlowQueries, searchQuery]);

  // Sort
  const sortedRows = useMemo(() => {
    const sorted = [...countyRows];
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'name':
          cmp = a.county_name.localeCompare(b.county_name);
          break;
        case 'efficiency':
          cmp = (a.efficiency_score ?? 999) - (b.efficiency_score ?? 999);
          break;
        case 'flagged':
          cmp = (b.flagged_amount ?? 0) - (a.flagged_amount ?? 0);
          break;
        case 'gap':
          cmp = b.total_gap - a.total_gap;
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [countyRows, sortKey, sortDir]);

  const toggleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortKey(key);
        setSortDir(key === 'name' ? 'asc' : 'asc');
      }
    },
    [sortKey]
  );

  const SortHeader = ({ label, field }: { label: string; field: SortKey }) => (
    <th
      className='py-2 pr-3 font-semibold text-gov-dark/70 cursor-pointer select-none group'
      onClick={() => toggleSort(field)}>
      <span className='inline-flex items-center gap-1'>
        {label}
        <ArrowUpDown
          size={12}
          className={`transition-colors ${
            sortKey === field ? 'text-gov-forest' : 'text-gray-300 group-hover:text-gray-400'
          }`}
        />
      </span>
    </th>
  );

  return (
    <PageShell
      title='Follow the Money'
      subtitle='Trace how public funds flow from allocation to expenditure across all 47 counties'>
      {/* ═══ A. YEAR SELECTOR ═══ */}
      <Section>
        <div className='flex items-center justify-between'>
          <h2 className='font-display text-xl text-gov-dark'>National Money Flow</h2>
          <YearSelector value={selectedYear} onChange={setSelectedYear} years={years} />
        </div>
      </Section>

      {/* ═══ B. NATIONAL WATERFALL ═══ */}
      <Section delay={0.05}>
        <div className='bg-white rounded-xl border border-gray-200 shadow-sm p-6'>
          <FollowTheMoney data={nationalFlow} isLoading={nationalLoading} />
        </div>
      </Section>

      {/* ═══ C. COUNTY COMPARISON TABLE ═══ */}
      <Section delay={0.1}>
        <div className='space-y-3'>
          <div className='flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3'>
            <div>
              <h2 className='font-display text-xl text-gov-dark'>County Comparison</h2>
              <p className='text-sm text-gov-dark/50'>
                Compare how efficiently each county manages public funds
              </p>
            </div>
            {/* Search */}
            <div className='relative'>
              <Search size={14} className='absolute left-3 top-1/2 -translate-y-1/2 text-gray-400' />
              <input
                type='text'
                placeholder='Search county...'
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className='pl-8 pr-3 py-1.5 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-gov-sage/30 focus:border-gov-sage w-56'
              />
            </div>
          </div>

          {/* Quick sort buttons */}
          <div className='flex flex-wrap gap-2'>
            {[
              { key: 'efficiency' as SortKey, label: 'Least Efficient' },
              { key: 'flagged' as SortKey, label: 'Most Flagged' },
              { key: 'gap' as SortKey, label: 'Highest Gap' },
              { key: 'name' as SortKey, label: 'A-Z' },
            ].map((btn) => (
              <button
                key={btn.key}
                onClick={() => toggleSort(btn.key)}
                className={`text-xs px-3 py-1 rounded-full transition-colors ${
                  sortKey === btn.key
                    ? 'bg-gov-forest text-white'
                    : 'bg-gov-dark/5 text-gov-dark/60 hover:bg-gov-dark/10'
                }`}>
                {btn.label}
              </button>
            ))}
          </div>

          {allCountyFlowsLoading || countiesLoading ? (
            <div className='flex items-center justify-center py-16'>
              <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
              <span className='ml-3 text-gov-dark/60 font-medium'>Loading county data...</span>
            </div>
          ) : (
            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='border-b border-gov-dark/10 text-left'>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 w-8'>#</th>
                    <SortHeader label='County' field='name' />
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 text-right'>Allocated</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 text-right'>Spent</th>
                    <SortHeader label='Efficiency' field='efficiency' />
                    <SortHeader label='Flagged' field='flagged' />
                    <SortHeader label='Total Gap' field='gap' />
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row, i) => (
                    <tr
                      key={row.county_id}
                      className='border-b border-gov-dark/5 hover:bg-gov-forest/[0.03] transition-colors'>
                      <td className='py-2.5 pr-3 text-gov-dark/40 font-mono text-xs'>{i + 1}</td>
                      <td className='py-2.5 pr-3'>
                        <Link
                          href={`/counties/${row.county_id}?tab=money`}
                          className='text-gov-forest font-medium hover:underline'>
                          {row.county_name}
                        </Link>
                      </td>
                      <td className='py-2.5 pr-3 text-right font-mono text-xs'>
                        {row.allocated != null ? fmtKES(row.allocated) : '—'}
                      </td>
                      <td className='py-2.5 pr-3 text-right font-mono text-xs'>
                        {row.spent != null ? fmtKES(row.spent) : '—'}
                      </td>
                      <td className='py-2.5 pr-3'>
                        {row.efficiency_score != null ? (
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                              row.efficiency_score >= 70
                                ? 'bg-emerald-100 text-emerald-700'
                                : row.efficiency_score >= 50
                                  ? 'bg-amber-100 text-amber-700'
                                  : 'bg-red-100 text-red-700'
                            }`}>
                            {row.efficiency_score.toFixed(1)}%
                          </span>
                        ) : (
                          <span className='text-gray-300'>—</span>
                        )}
                      </td>
                      <td className='py-2.5 pr-3 text-right font-mono text-red-600 text-xs'>
                        {row.flagged_amount != null && row.flagged_amount > 0
                          ? fmtKES(row.flagged_amount)
                          : '—'}
                      </td>
                      <td className='py-2.5 text-right font-mono text-amber-600 text-xs'>
                        {row.total_gap > 0 ? fmtKES(row.total_gap) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!allCountyFlowsLoading && sortedRows.length === 0 && (
            <div className='text-center py-12 text-gov-dark/40'>
              {searchQuery ? 'No counties match your search.' : 'No data available.'}
            </div>
          )}
        </div>
      </Section>
    </PageShell>
  );
}
