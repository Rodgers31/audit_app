'use client';

import InfoTip from '@/components/InfoTip';
import { useAuditDashboardSummary } from '@/lib/react-query';
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

const OPINION_COLORS: Record<string, string> = {
  unqualified: '#4A7C5C',
  qualified: '#D9A441',
  adverse: '#C94A4A',
  disclaimer: '#9CA3AF',
};

const OPINION_INFOTIP: Record<string, string> = {
  unqualified: 'audit-clean',
  qualified: 'audit-qualified',
  adverse: 'audit-adverse',
  disclaimer: 'audit-disclaimer',
};

const DEFAULT_COLOR = '#6B7280';

function formatKES(billions: number): string {
  if (billions >= 1000) return `KES ${(billions / 1000).toFixed(1)}T`;
  return `KES ${billions.toFixed(0)}B`;
}

/**
 * Audit Transparency Reports panel.
 * Donut chart of audit opinion distribution + issues summary.
 * Data sourced from GET /audit/summary.
 */
export default function AuditTransparencyCard() {
  const { data, isLoading } = useAuditDashboardSummary();

  const opinionEntries = Object.entries(data?.findings_by_opinion ?? {});
  const totalOpinions = opinionEntries.reduce((sum, [, v]) => sum + v, 0);

  const auditStatusData = opinionEntries.map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: totalOpinions > 0 ? Math.round((value / totalOpinions) * 100) : 0,
    color: OPINION_COLORS[name.toLowerCase()] ?? DEFAULT_COLOR,
    infoTip: OPINION_INFOTIP[name.toLowerCase()],
  }));

  const totalIrregular =
    (data?.total_irregular_expenditure ?? 0) + (data?.total_unsupported_expenditure ?? 0);
  const totalFindings = data?.total_findings ?? 0;
  const worstCountiesCount = data?.worst_counties?.length ?? 0;

  if (isLoading) {
    return (
      <div className='glass-card p-6 sm:p-8 animate-pulse'>
        <div className='h-6 bg-neutral-200 rounded w-48 mb-5' />
        <div className='h-44 bg-neutral-100 rounded mb-4' />
        <div className='h-24 bg-neutral-100 rounded' />
      </div>
    );
  }

  if (!opinionEntries.length) {
    return (
      <div className='glass-card p-6 sm:p-8'>
        <h3 className='font-display text-xl text-gov-dark dark:text-white mb-5'>Audit Transparency Reports</h3>
        <p className='text-sm text-neutral-muted'>Audit data unavailable.</p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.2 }}
      className='glass-card p-6 sm:p-8'>
      <h3 className='font-display text-xl text-gov-dark dark:text-white mb-5'>Audit Transparency Reports</h3>

      <p className='text-xs text-neutral-muted uppercase tracking-wider mb-3 font-medium'>
        Audit Opinion Distribution
      </p>

      {/* Donut chart */}
      <div className='h-44 mb-4'>
        <ResponsiveContainer width='100%' height='100%'>
          <PieChart>
            <Pie
              data={auditStatusData}
              cx='50%'
              cy='50%'
              innerRadius={36}
              outerRadius={64}
              paddingAngle={3}
              dataKey='value'
              stroke='none'>
              {auditStatusData.map((entry, i) => (
                <Cell key={i} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: 'rgba(255,255,255,0.9)',
                border: '1px solid #E2DDD5',
                borderRadius: '8px',
                fontSize: '11px',
              }}
              formatter={(value: number, name: string) => [`${value}%`, name]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className='grid grid-cols-2 gap-x-4 gap-y-2 mb-6'>
        {auditStatusData.map((d) => (
          <div key={d.name} className='flex items-center gap-2'>
            <div
              className='w-2.5 h-2.5 rounded-full flex-shrink-0'
              style={{ background: d.color }}
            />
            <div className='flex items-center gap-1'>
              <span className='text-xs text-neutral-muted'>{d.name}</span>
              {d.infoTip && <InfoTip term={d.infoTip} size={10} />}
            </div>
            <span className='ml-auto text-xs font-semibold tabular-nums' style={{ color: d.color }}>
              {d.value}%
            </span>
          </div>
        ))}
      </div>

      {/* Unresolved issues callout */}
      <div className='bg-gov-copper/5 rounded-xl px-4 py-3 border border-gov-copper/10 mb-4'>
        <div className='flex items-center gap-2 mb-1'>
          <AlertTriangle className='w-4 h-4 text-gov-copper' />
          <span className='text-sm font-semibold text-gov-copper'>Unresolved Issues</span>
        </div>
        <div className='flex items-baseline gap-2'>
          <span className='text-lg font-bold text-gov-dark dark:text-white tabular-nums'>
            {formatKES(totalIrregular)}
          </span>
          <span className='text-xs text-neutral-muted'>{totalFindings} flagged by auditors</span>
        </div>
      </div>

      {/* High risk counties */}
      {worstCountiesCount > 0 && (
        <div className='flex items-center gap-2'>
          <AlertTriangle className='w-4 h-4 text-gov-copper flex-shrink-0' />
          <div>
            <span className='text-sm font-semibold text-gov-dark dark:text-white'>High Risk Counties</span>
            <span className='text-xs text-neutral-muted block'>
              {worstCountiesCount} identified with major financial findings
            </span>
          </div>
        </div>
      )}
    </motion.div>
  );
}
