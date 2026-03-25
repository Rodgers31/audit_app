'use client';

import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import InfoTip from '@/components/InfoTip';

const auditStatusData = [
  { name: 'Complete', value: 51, color: '#4A7C5C' },
  { name: 'Overspending', value: 29, color: '#C94A4A' },
  { name: 'Average', value: 29, color: '#D9A441' },
  { name: 'Pending', value: 37, color: '#9CA3AF' },
];

/**
 * Audit Transparency Reports panel.
 * Donut chart of 2024 audit statuses + issues summary.
 */
export default function AuditTransparencyCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.2 }}
      className='glass-card p-6 sm:p-8'>
      <h3 className='font-display text-xl text-gov-dark mb-5'>Audit Transparency Reports</h3>

      <p className='text-xs text-neutral-muted uppercase tracking-wider mb-3 font-medium'>
        Audit Status of 2024 Reports
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
              {(d.name === 'Complete' ||
                d.name === 'Overspending' ||
                d.name === 'Average' ||
                d.name === 'Pending') && (
                <InfoTip
                  term={
                    d.name === 'Complete'
                      ? 'audit-clean'
                      : d.name === 'Overspending'
                        ? 'audit-adverse'
                        : d.name === 'Average'
                          ? 'audit-qualified'
                          : 'audit-disclaimer'
                  }
                  size={10}
                />
              )}
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
          <span className='text-lg font-bold text-gov-dark tabular-nums'>KES 5.1T</span>
          <span className='text-xs text-neutral-muted'>
            47 flagged by auditors across all solo treasuries
          </span>
        </div>
      </div>

      {/* High risk counties */}
      <div className='flex items-center gap-2'>
        <AlertTriangle className='w-4 h-4 text-gov-copper flex-shrink-0' />
        <div>
          <span className='text-sm font-semibold text-gov-dark'>High Risk Counties</span>
          <span className='text-xs text-neutral-muted block'>
            19 identified with major financial misappropriation
          </span>
        </div>
      </div>
    </motion.div>
  );
}
