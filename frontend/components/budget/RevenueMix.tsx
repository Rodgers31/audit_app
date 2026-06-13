'use client';

/**
 * RevenueMix
 *
 * Who actually funds Kenya's government?
 *
 * Uses the latest FISCAL YEAR WITH ACTUALS (skipping current-year targets)
 * from the /budget/enhanced `revenue_by_source` series.
 *
 *   Top row:    horizontal stacked flow bar, per-source, largest-first.
 *   Middle:     per-source card grid with YoY deltas, 3-year sparklines,
 *               and a plain-English one-liner describing what the source is.
 *
 * The narrative callout on hover picks out the single largest source and
 * tells the user, "every time you buy fuel, pay rent, or earn wages, you
 * contribute via these tax streams."
 */

import { motion } from 'framer-motion';
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { useMemo, useState } from 'react';

export interface RevSource {
  revenue_type: string;
  category?: string | null;
  amount?: number | null; // KES billions
  target?: number | null;
  share_pct?: number | null;
  yoy_growth_pct?: number | null;
}

export interface RevFy {
  fiscal_year: string;
  sources: RevSource[];
}

/* ─── Palette — each tax stream tagged in a distinct but muted hue so the
   mix feels editorial rather than dashboard-y. Muted saturation keeps the
   revenue section visually distinct from the red/green hero flow. ─── */
const SOURCE_PALETTE: Record<string, { start: string; end: string; accent: string }> = {
  PAYE: { start: '#3B6FA8', end: '#20477A', accent: '#2F5A8F' },
  'Corporation Tax': { start: '#5B5591', end: '#2F2A63', accent: '#423C7A' },
  VAT: { start: '#3F7A5A', end: '#1F4A30', accent: '#2F6343' },
  'Excise Duty': { start: '#B38628', end: '#7D591A', accent: '#A6781F' },
  'Customs & Import Duty': { start: '#B84A4A', end: '#7E2424', accent: '#9E3030' },
  'Other Tax Revenue': { start: '#7C8794', end: '#4B5563', accent: '#5B6672' },
  'Total Tax Revenue': { start: '#1B3A2A', end: '#0F1A12', accent: '#1B3A2A' },
  'Total Government Revenue': { start: '#1B3A2A', end: '#0F1A12', accent: '#1B3A2A' },
};

const FALLBACK_PAL = { start: '#6B7280', end: '#3F4754', accent: '#4B5563' };

const SOURCE_DESC: Record<string, string> = {
  PAYE: 'Pay-As-You-Earn — income tax withheld from salaries by employers.',
  'Corporation Tax': "Tax on businesses' profits, paid quarterly by companies.",
  VAT: 'Value-Added Tax — the 16% on most goods and services you buy.',
  'Excise Duty': 'Specific-rate tax on fuel, alcohol, tobacco, airtime, sugar.',
  'Customs & Import Duty': 'Duties at the port on imported goods plus import VAT.',
  'Other Tax Revenue': 'Stamp duty, agricultural cess, minor taxes lumped together.',
};

function paletteFor(name: string) {
  return SOURCE_PALETTE[name] ?? FALLBACK_PAL;
}

function fmtB(v?: number | null): string {
  if (v == null || v <= 0) return '—';
  if (v >= 1000) return `${(v / 1000).toFixed(2)}T`;
  return `${v.toFixed(0)}B`;
}

/* ────────────────────────────── component ────────────────────────────── */

interface Props {
  revenueBySource: RevFy[];
}

export default function RevenueMix({ revenueBySource }: Props) {
  const [hoverKey, setHoverKey] = useState<string | null>(null);

  // Pick the latest FY that has multi-source actuals.
  const multiSourceActualFYs = useMemo(
    () =>
      (revenueBySource ?? []).filter(
        (fy) =>
          (fy.sources ?? []).length > 1 &&
          fy.sources.some((s) => s.amount != null && s.amount > 0)
      ),
    [revenueBySource]
  );

  const latest = multiSourceActualFYs[multiSourceActualFYs.length - 1];
  const prev = multiSourceActualFYs[multiSourceActualFYs.length - 2];

  // Rows for the latest year, excluding aggregate "Total …" rows.
  const rows = useMemo(() => {
    if (!latest) return [];
    const list = (latest.sources ?? [])
      .filter(
        (s) =>
          s.amount != null &&
          s.amount > 0 &&
          !/^total /i.test(s.revenue_type ?? '')
      )
      .sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0));
    const totalB = list.reduce((s, r) => s + (r.amount ?? 0), 0);

    // 3-year series per source for the sparkline
    const seriesFYs = multiSourceActualFYs.slice(-3);

    return list.map((r) => {
      const pal = paletteFor(r.revenue_type);
      const series = seriesFYs
        .map((fy) => {
          const row = (fy.sources ?? []).find((s) => s.revenue_type === r.revenue_type);
          return { year: fy.fiscal_year?.replace('FY ', '') ?? '', amount: row?.amount ?? null };
        })
        .filter((p) => p.amount != null && p.amount > 0) as { year: string; amount: number }[];
      const prevVal = prev?.sources?.find((s) => s.revenue_type === r.revenue_type)?.amount ?? null;
      const yoy =
        prevVal != null && prevVal > 0 && r.amount != null
          ? ((r.amount - prevVal) / prevVal) * 100
          : null;
      return {
        key: r.revenue_type,
        label: r.revenue_type,
        amount: r.amount ?? 0,
        share: totalB > 0 ? ((r.amount ?? 0) / totalB) * 100 : 0,
        yoy,
        pal,
        desc: SOURCE_DESC[r.revenue_type] ?? '',
        series,
        totalB,
      };
    });
  }, [latest, prev, multiSourceActualFYs]);

  if (!latest || rows.length === 0) return null;

  const totalB = rows[0]?.totalB ?? 0;
  const topSource = rows[0];

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.55 }}
      className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-7'>
      <div className='flex items-start justify-between gap-4 flex-wrap mb-4'>
        <div>
          <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/80 dark:text-emerald-100/80'>
            Where tax revenue comes from
          </div>
          <h3 className='font-display text-xl sm:text-[22px] text-gov-dark dark:text-white leading-tight mt-0.5'>
            How KRA collected KES {fmtB(totalB)} in {latest.fiscal_year}
          </h3>
          <p className='text-[12.5px] text-neutral-muted mt-1 max-w-2xl'>
            Tax revenue broken down by stream — shares are of{' '}
            <strong className='font-semibold text-gov-dark dark:text-white'>tax revenue</strong>, excluding
            non-tax revenue (fees, investment income, A-in-A, and grants).{' '}
            {topSource?.label} is the single largest — {topSource?.share.toFixed(0)}% of tax revenue.
          </p>
        </div>
        <div className='text-right'>
          <div className='text-[10.5px] uppercase tracking-wider font-semibold text-neutral-muted'>
            Source
          </div>
          <div className='text-[12px] font-semibold text-gov-dark dark:text-white'>KRA Annual Performance</div>
          <div className='text-[10.5px] text-neutral-muted'>FY {latest.fiscal_year}</div>
        </div>
      </div>

      {/* Flow bar */}
      <div className='relative w-full rounded-full h-11 bg-gov-sand/60 border border-neutral-border/30 overflow-hidden flex'>
        {rows.map((r, i) => {
          const w = r.share;
          if (w < 0.3) return null;
          const isHover = hoverKey === r.key;
          return (
            <motion.div
              key={r.key}
              initial={{ width: 0 }}
              animate={{ width: `${w}%` }}
              transition={{ duration: 0.9, delay: 0.07 * i, ease: [0.22, 1, 0.36, 1] }}
              onMouseEnter={() => setHoverKey(r.key)}
              onMouseLeave={() => setHoverKey(null)}
              className='relative h-full cursor-default'
              style={{
                background: `linear-gradient(135deg, ${r.pal.start}, ${r.pal.end})`,
                filter: isHover ? 'brightness(1.08)' : 'brightness(1)',
                transform: isHover ? 'scaleY(1.06)' : 'scaleY(1)',
                transformOrigin: 'center',
                transition: 'filter .2s, transform .2s',
              }}>
              {w > 8 && (
                <span className='absolute inset-0 flex items-center justify-center px-2 text-[11px] font-bold text-white/95 drop-shadow-sm tabular-nums'>
                  {w.toFixed(0)}%
                </span>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Source cards */}
      <div className='mt-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5'>
        {rows.map((r) => {
          const isHover = hoverKey === r.key;
          const yoyUp = r.yoy != null && r.yoy > 0.5;
          const yoyDown = r.yoy != null && r.yoy < -0.5;
          return (
            <div
              key={r.key}
              onMouseEnter={() => setHoverKey(r.key)}
              onMouseLeave={() => setHoverKey(null)}
              className={`relative rounded-xl bg-white dark:bg-surface-base border overflow-hidden transition-all ${
                isHover ? 'border-neutral-border/80 shadow-elevated' : 'border-neutral-border/30 shadow-sm'
              }`}>
              {/* Left accent stripe */}
              <div
                className='absolute left-0 top-0 bottom-0 w-1'
                style={{
                  background: `linear-gradient(180deg, ${r.pal.start}, ${r.pal.end})`,
                }}
              />
              <div className='pl-4 pr-3 py-3'>
                <div className='flex items-baseline justify-between gap-2 mb-1'>
                  <span className='text-[12px] font-semibold text-gov-dark dark:text-white truncate'>
                    {r.label}
                  </span>
                  <span
                    className='text-[11px] font-bold tabular-nums'
                    style={{ color: r.pal.accent }}>
                    {r.share.toFixed(1)}%
                  </span>
                </div>
                <div className='flex items-baseline justify-between gap-2'>
                  <div className='text-base font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight'>
                    KES {fmtB(r.amount)}
                  </div>
                  {r.yoy != null && (
                    <span
                      className={`inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full tabular-nums ${
                        yoyUp
                          ? 'bg-green-50 text-green-700'
                          : yoyDown
                            ? 'bg-red-50 text-red-600'
                            : 'bg-gray-100 dark:bg-surface-elevated text-gray-500 dark:text-neutral-muted/80'
                      }`}>
                      {yoyUp ? <ArrowUp size={11} /> : yoyDown ? <ArrowDown size={11} /> : <Minus size={11} />}
                      {Math.abs(r.yoy).toFixed(1)}%
                    </span>
                  )}
                </div>
                {/* Mini multi-year bar */}
                {r.series.length > 1 && (
                  <div className='mt-2 flex items-end gap-1 h-6'>
                    {r.series.map((p, i) => {
                      const max = Math.max(...r.series.map((s) => s.amount));
                      const h = (p.amount / max) * 100;
                      const isLatest = i === r.series.length - 1;
                      return (
                        <div
                          key={p.year}
                          className='flex-1 flex flex-col items-center gap-0.5'>
                          <div
                            className='w-full rounded-t-sm transition-all'
                            style={{
                              height: `${Math.max(h, 10)}%`,
                              background: isLatest
                                ? `linear-gradient(180deg, ${r.pal.start}, ${r.pal.end})`
                                : '#E2DDD5',
                            }}
                          />
                          <span className='text-[8px] text-neutral-muted tabular-nums'>
                            {p.year}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {r.desc && (
                  <p className='mt-2 text-[10.5px] text-neutral-muted leading-snug'>
                    {r.desc}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </motion.section>
  );
}
