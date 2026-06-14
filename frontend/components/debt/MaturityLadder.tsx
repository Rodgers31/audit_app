'use client';

import { motion } from 'framer-motion';
import { AlertTriangle, Calendar, Info } from 'lucide-react';
import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { NationalLoan } from '@/lib/api/debt';

interface MaturityLadderProps {
  loans: NationalLoan[];
}

function parseYear(date: string | null | undefined): number | null {
  if (!date) return null;
  const match = /^(\d{4})/.exec(date);
  if (!match) return null;
  const yr = parseInt(match[1], 10);
  if (!Number.isFinite(yr) || yr < 1990 || yr > 2100) return null;
  return yr;
}

function categoryTone(type: string): { bar: string; label: string } {
  const t = type.toLowerCase();
  if (t.includes('bilateral')) return { bar: '#8b5cf6', label: 'Bilateral' };
  if (t.includes('multilateral')) return { bar: '#3b82f6', label: 'Multilateral' };
  if (t.includes('commercial') || t.includes('eurobond'))
    return { bar: '#C94A4A', label: 'Commercial / Eurobond' };
  if (t.includes('bond')) return { bar: '#0D7377', label: 'Domestic Bond' };
  if (t.includes('tbill') || t.includes('bill')) return { bar: '#D9A441', label: 'Treasury Bill' };
  if (t.includes('cbk') || t.includes('overdraft')) return { bar: '#6366f1', label: 'CBK Advance' };
  return { bar: '#4A7C5C', label: 'Other' };
}

function fmtT(val: number): string {
  if (val >= 1_000_000_000_000) return `${(val / 1_000_000_000_000).toFixed(2)}T`;
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  return val.toLocaleString();
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className='rounded-xl bg-white/95 backdrop-blur-lg border border-neutral-border/40 shadow-elevated px-4 py-3 text-xs'>
      <p className='font-display text-sm text-gov-dark dark:text-white mb-1'>{label}</p>
      <div className='flex justify-between gap-6 mb-1'>
        <span className='text-neutral-muted'>Due this year</span>
        <span className='font-bold text-gov-dark dark:text-white tabular-nums'>KES {fmtT(d.total)}</span>
      </div>
      {d.loans?.length > 0 && (
        <div className='pt-2 border-t border-neutral-border/30 space-y-1'>
          {d.loans.map((l: any) => (
            <div key={l.lender} className='flex justify-between gap-6'>
              <span className='text-neutral-muted flex items-center gap-1.5'>
                <span className='w-2 h-2 rounded-full' style={{ background: l.color }} />
                {l.lender}
              </span>
              <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>
                {fmtT(l.outstanding)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function MaturityLadder({ loans }: MaturityLadderProps) {
  const { buckets, revolving, largest, totalDated, currentYear, yearRange } = useMemo(() => {
    const now = new Date();
    const cy = now.getFullYear();

    const dated: Array<{ year: number; loan: NationalLoan; tone: ReturnType<typeof categoryTone> }> = [];
    const revolvingList: Array<{ loan: NationalLoan; tone: ReturnType<typeof categoryTone> }> = [];

    for (const l of loans) {
      const yr = parseYear(l.maturity_date);
      const tone = categoryTone(l.lender_type);
      if (yr && yr >= cy - 1) {
        dated.push({ year: yr, loan: l, tone });
      } else {
        revolvingList.push({ loan: l, tone });
      }
    }

    const minYear = dated.length ? Math.min(...dated.map((d) => d.year)) : cy;
    const maxYear = dated.length ? Math.max(...dated.map((d) => d.year)) : cy + 5;
    const bucketMap = new Map<number, { year: number; total: number; loans: any[] }>();

    for (let y = Math.min(minYear, cy); y <= maxYear; y += 1) {
      bucketMap.set(y, { year: y, total: 0, loans: [] });
    }

    for (const d of dated) {
      const bucket = bucketMap.get(d.year);
      if (!bucket) continue;
      const amt = d.loan.outstanding_numeric || parseFloat(d.loan.outstanding || '0') || 0;
      bucket.total += amt;
      bucket.loans.push({
        lender: d.loan.lender,
        outstanding: amt,
        color: d.tone.bar,
      });
    }

    const arr = Array.from(bucketMap.values()).sort((a, b) => a.year - b.year);
    const totalDatedSum = arr.reduce((s, b) => s + b.total, 0);
    const largestBucket = [...arr].sort((a, b) => b.total - a.total)[0];

    return {
      buckets: arr,
      revolving: revolvingList,
      largest: largestBucket,
      totalDated: totalDatedSum,
      currentYear: cy,
      yearRange: arr.length ? `${arr[0].year}–${arr[arr.length - 1].year}` : '—',
    };
  }, [loans]);

  const datedCount = buckets.reduce((s, b) => s + b.loans.length, 0);
  const hasData = buckets.length > 0 && totalDated > 0;

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <h3 className='font-display text-xl sm:text-2xl text-gov-dark dark:text-white flex items-center gap-2'>
            <Calendar className='text-gov-forest dark:text-emerald-100' size={22} />
            When the bills come due
          </h3>
          <p className='text-sm text-neutral-muted mt-1'>
            Outstanding balance per maturity year — the &ldquo;walls&rdquo; of debt Kenya must refinance
            or pay off.
          </p>
        </div>
        {largest && largest.total > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2 }}
            className='rounded-lg bg-gov-copper/10 border border-gov-copper/30 px-3 py-2'>
            <div className='text-[10px] uppercase tracking-wider text-gov-copper font-semibold'>
              Biggest wall
            </div>
            <div className='text-lg font-bold text-gov-dark dark:text-white tabular-nums'>
              {largest.year} — KES {fmtT(largest.total)}
            </div>
          </motion.div>
        )}
      </div>

      {hasData ? (
        <div className='rounded-xl bg-white/70 dark:bg-surface-elevated border border-white/70 shadow-surface p-4 sm:p-5'>
          <ResponsiveContainer width='100%' height={320}>
            <BarChart data={buckets} margin={{ top: 16, right: 12, left: 0, bottom: 8 }}>
              <defs>
                <linearGradient id='maturityBarFill' x1='0' y1='0' x2='0' y2='1'>
                  <stop offset='0%' stopColor='#C94A4A' stopOpacity={0.95} />
                  <stop offset='100%' stopColor='#8C2E2E' stopOpacity={0.85} />
                </linearGradient>
                <linearGradient id='maturityBarFillCurrent' x1='0' y1='0' x2='0' y2='1'>
                  <stop offset='0%' stopColor='#D9A441' stopOpacity={0.95} />
                  <stop offset='100%' stopColor='#BA8B33' stopOpacity={0.85} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray='3 3' stroke='#E2DDD5' vertical={false} />
              <XAxis
                dataKey='year'
                tick={{ fill: '#6B7280', fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: '#E2DDD5' }}
              />
              <YAxis
                tickFormatter={(v) => fmtT(v)}
                tick={{ fill: '#6B7280', fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: '#E2DDD5' }}
                width={70}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(201,74,74,0.08)' }} />
              <ReferenceLine
                x={currentYear}
                stroke='#4A7C5C'
                strokeWidth={2}
                strokeDasharray='4 4'
                label={{
                  value: `Today (${currentYear})`,
                  position: 'top',
                  fill: '#4A7C5C',
                  fontSize: 11,
                  fontWeight: 600,
                }}
              />
              <Bar dataKey='total' radius={[6, 6, 0, 0]} maxBarSize={64}>
                {buckets.map((b) => (
                  <Cell
                    key={b.year}
                    fill={
                      b.year === currentYear
                        ? 'url(#maturityBarFillCurrent)'
                        : 'url(#maturityBarFill)'
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className='text-[11px] text-neutral-muted mt-2'>
            Showing {datedCount} loans with published maturity dates across {yearRange}. Dashed
            green line marks today.
          </p>
        </div>
      ) : (
        <div className='rounded-xl bg-white/60 dark:bg-surface-elevated border border-white/60 p-8 text-center text-sm text-neutral-muted'>
          No dated maturity profile available yet.
        </div>
      )}

      {revolving.length > 0 && (
        <div className='rounded-xl bg-gradient-to-br from-gov-sand/50 to-gov-cream/30 border border-gov-sage/25 p-4 sm:p-5'>
          <div className='flex items-start gap-2.5 mb-3'>
            <Info className='text-gov-forest dark:text-emerald-100 flex-shrink-0 mt-0.5' size={18} />
            <div>
              <h4 className='text-sm font-semibold text-gov-dark dark:text-white'>
                Revolving &amp; pooled instruments
              </h4>
              <p className='text-[11px] text-neutral-muted mt-0.5'>
                Continuously rolled over — no single maturity date. Interest costs recur every
                year.
              </p>
            </div>
          </div>
          <div className='grid grid-cols-1 sm:grid-cols-2 gap-2'>
            {revolving.map(({ loan, tone }) => {
              const amt = loan.outstanding_numeric || parseFloat(loan.outstanding || '0') || 0;
              return (
                <div
                  key={loan.lender}
                  className='flex items-center gap-2 rounded-lg bg-white/70 dark:bg-surface-elevated border border-white/60 px-3 py-2'>
                  <span
                    className='w-2.5 h-2.5 rounded-full flex-shrink-0'
                    style={{ backgroundColor: tone.bar }}
                  />
                  <div className='flex-1 min-w-0 flex items-baseline justify-between gap-2'>
                    <span className='text-xs font-medium text-gov-dark dark:text-white truncate'>
                      {loan.lender}
                    </span>
                    <span className='text-xs text-neutral-muted tabular-nums flex-shrink-0'>
                      KES {fmtT(amt)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
