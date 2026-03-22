'use client';

import { SkeletonCard } from '@/components/ui/Skeleton';
import { useAuditStatistics } from '@/lib/react-query/useAudits';
import { motion } from 'framer-motion';
import { AlertTriangle, MapPin, ShieldAlert, ShieldCheck } from 'lucide-react';
import Link from 'next/link';

function fmtB(val: number): string {
  if (val >= 1_000_000_000_000) return `${(val / 1_000_000_000_000).toFixed(1)}T`;
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  return val.toLocaleString();
}

export default function AccountabilityPulseCard() {
  const { data: stats, isLoading, error } = useAuditStatistics();

  if (isLoading) {
    return <SkeletonCard className='min-h-[340px]' />;
  }

  if (error || !stats) {
    return (
      <div className='glass-card p-8 flex flex-col items-center justify-center min-h-[340px] gap-2'>
        <ShieldAlert className='w-6 h-6 text-neutral-muted/25' />
        <p className='text-xs text-neutral-muted'>Audit statistics unavailable</p>
      </div>
    );
  }

  const bySev = stats.by_severity || {};
  const critical = bySev.critical || bySev.CRITICAL || 0;
  const warning = bySev.warning || bySev.WARNING || 0;
  const info = bySev.info || bySev.INFO || 0;
  const total = critical + warning + info || 1;
  const topCounties = (stats.top_flagged_counties || []).slice(0, 5);
  const recentCritical = (stats.recent_critical || []).slice(0, 3);

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.2 }}
      className='glass-card overflow-hidden'>
      {/* Header */}
      <div className='bg-gradient-to-r from-gov-copper/[0.06] via-gov-sand/40 to-transparent px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border/20'>
        <h3 className='font-display text-lg text-gov-dark mb-0.5'>Accountability Pulse</h3>
        <p className='text-xs text-neutral-muted'>
          Audit findings across {stats.counties_audited || '--'} counties &amp; national government
        </p>
      </div>

      <div className='px-6 sm:px-8 py-5'>
        {/* Headline metrics */}
        <div className='grid grid-cols-3 gap-3 mb-5'>
          <div className='rounded-xl bg-gov-copper/[0.05] border border-neutral-border/30 px-3 py-3 text-center'>
            <ShieldAlert className='w-4 h-4 text-gov-copper mx-auto mb-1.5 opacity-70' />
            <span className='block text-lg font-bold text-gov-copper tabular-nums leading-none'>
              {critical}
            </span>
            <span className='text-[10px] text-neutral-muted mt-1 block'>Critical</span>
          </div>
          <div className='rounded-xl bg-gov-gold/[0.06] border border-neutral-border/30 px-3 py-3 text-center'>
            <AlertTriangle className='w-4 h-4 text-gov-gold mx-auto mb-1.5 opacity-70' />
            <span className='block text-lg font-bold text-gov-gold tabular-nums leading-none'>
              {warning}
            </span>
            <span className='text-[10px] text-neutral-muted mt-1 block'>Significant</span>
          </div>
          <div className='rounded-xl bg-gov-sage/[0.05] border border-neutral-border/30 px-3 py-3 text-center'>
            <ShieldCheck className='w-4 h-4 text-gov-sage mx-auto mb-1.5 opacity-70' />
            <span className='block text-lg font-bold text-gov-sage tabular-nums leading-none'>
              {info}
            </span>
            <span className='text-[10px] text-neutral-muted mt-1 block'>Minor</span>
          </div>
        </div>

        {/* Stacked severity bar */}
        <div className='mb-5'>
          <div className='flex items-center justify-between mb-1.5'>
            <span className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider'>
              Finding Distribution
            </span>
            <span className='text-xs font-semibold text-gov-dark tabular-nums'>
              {stats.total_findings || total} total
            </span>
          </div>
          <div className='flex h-3 rounded-full overflow-hidden bg-neutral-border/20'>
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${(critical / total) * 100}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.7 }}
              className='bg-gov-copper rounded-l-full'
            />
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${(warning / total) * 100}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.7, delay: 0.1 }}
              className='bg-gov-gold'
            />
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${(info / total) * 100}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.7, delay: 0.2 }}
              className='bg-gov-sage rounded-r-full'
            />
          </div>
        </div>

        {/* Amount flagged callout */}
        {stats.total_amount_flagged > 0 && (
          <div className='rounded-xl bg-gov-copper/[0.05] border border-gov-copper/10 px-4 py-3 mb-5 flex items-center gap-3'>
            <div className='w-9 h-9 rounded-lg bg-gov-copper/10 flex items-center justify-center flex-shrink-0'>
              <AlertTriangle className='w-4 h-4 text-gov-copper' />
            </div>
            <div>
              <span className='text-sm font-bold text-gov-dark tabular-nums'>
                KES {fmtB(stats.total_amount_flagged)}
              </span>
              <p className='text-[11px] text-neutral-muted leading-snug'>
                in public funds flagged by auditors
              </p>
            </div>
          </div>
        )}

        {/* Top flagged counties */}
        <div className='mb-5'>
          <p className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider mb-3'>
            Most Flagged Counties
          </p>
          <div className='space-y-2'>
            {topCounties.map((c: any, i: number) => (
              <div
                key={c.county}
                className='flex items-center gap-2.5 rounded-lg bg-white/40 border border-neutral-border/20 px-3 py-2'>
                <span className='w-5 h-5 rounded-md bg-gov-copper/10 flex items-center justify-center flex-shrink-0'>
                  <MapPin className='w-3 h-3 text-gov-copper' />
                </span>
                <span className='text-xs text-gov-dark font-medium flex-1 truncate'>
                  {c.county}
                </span>
                <span className='text-[11px] font-bold text-gov-copper tabular-nums'>
                  {c.critical_count} critical
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Recent critical - just a teaser */}
        {recentCritical.length > 0 && (
          <div className='mb-5'>
            <p className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider mb-2'>
              Latest Critical Finding
            </p>
            <div className='rounded-lg border-l-[3px] border-l-gov-copper bg-gov-copper/[0.04] px-4 py-2.5'>
              <p className='text-xs text-gov-dark leading-relaxed line-clamp-2'>
                {recentCritical[0].finding}
              </p>
              <p className='text-[10px] text-neutral-muted mt-1'>
                {recentCritical[0].county} · {recentCritical[0].fiscal_year}
              </p>
            </div>
          </div>
        )}

        <Link
          href='/counties'
          className='group flex items-center justify-center gap-1.5 w-full rounded-lg bg-white/60 border border-neutral-border/40 hover:border-gov-copper/30 hover:bg-gov-copper/[0.03] px-4 py-2.5 transition-all text-xs font-medium text-gov-dark'>
          Explore County Audits →
        </Link>
      </div>
    </motion.div>
  );
}
