'use client';

import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Sector } from 'recharts';

interface CategoryBreakdown {
  category: string;
  label: string;
  outstanding: number;
  share: number;
  lenders?: Array<{
    lender: string;
    outstanding: number;
    rate?: number | string | null;
    annual_service_cost?: number | null;
  }>;
}

interface LenderTreemapProps {
  categories: CategoryBreakdown[];
  totalOutstanding: number;
}

/* ──────────────────────────────── tokens ──────────────────────────────── */

// Refined tonal palettes — category → (base, gradStart, gradEnd).
// Kept within ~15% luminance range per slice to avoid a "cartoon rainbow"
// look; each external slice is a distinct deep red, each domestic slice is a
// distinct deep green, with the gold strictly reserved for pending bills.
const PALETTE: Record<string, { base: string; start: string; end: string }> = {
  // External reds — burgundy → brick → rust → claret
  external_multilateral: { base: '#9E3030', start: '#AB3A3A', end: '#7E2424' },
  external_bilateral: { base: '#6F2222', start: '#843030', end: '#4C1616' },
  external_commercial: { base: '#B83E3E', start: '#C54B4B', end: '#8E2A2A' },
  external_eurobond: { base: '#A23535', start: '#AE3F3F', end: '#7A2626' },
  // Domestic greens — deep forest → sage → moss
  domestic_bonds: { base: '#2F6343', start: '#3B7251', end: '#1F4A30' },
  domestic_bills: { base: '#3E7655', start: '#4B8564', end: '#295B3E' },
  domestic_overdraft: { base: '#35684A', start: '#41785A', end: '#234C33' },
  domestic_legacy: { base: '#234E33', start: '#2F5D40', end: '#183823' },
  cbk_advance: { base: '#2A5A3B', start: '#366B48', end: '#1B4128' },
  // Pending bills — muted ochre
  pending_bills: { base: '#A6781F', start: '#B38628', end: '#7D591A' },
};

const FALLBACK_EXT = { base: '#A23535', start: '#AE3F3F', end: '#7A2626' };
const FALLBACK_DOM = { base: '#2F6343', start: '#3B7251', end: '#1F4A30' };
const FALLBACK_GOLD = { base: '#A6781F', start: '#B38628', end: '#7D591A' };

function paletteFor(cat: string): { base: string; start: string; end: string } {
  const key = cat.toLowerCase();
  if (PALETTE[key]) return PALETTE[key];
  if (key.includes('pending')) return FALLBACK_GOLD;
  if (
    key.includes('external') ||
    key.includes('multilateral') ||
    key.includes('bilateral') ||
    key.includes('commercial') ||
    key.includes('eurobond')
  )
    return FALLBACK_EXT;
  return FALLBACK_DOM;
}

function isPending(cat: string): boolean {
  return cat.toLowerCase().includes('pending');
}

function isExternal(cat: string): boolean {
  const k = cat.toLowerCase();
  if (isPending(k)) return false;
  return (
    k.includes('external') ||
    k.includes('multilateral') ||
    k.includes('bilateral') ||
    k.includes('commercial') ||
    k.includes('eurobond')
  );
}

function isDomestic(cat: string): boolean {
  const k = cat.toLowerCase();
  if (isPending(k)) return false;
  if (isExternal(k)) return false;
  return (
    k.includes('domestic') ||
    k.includes('bond') ||
    k.includes('tbill') ||
    k.includes('bill') ||
    k.includes('cbk') ||
    k.includes('overdraft') ||
    k.includes('legacy')
  );
}

function fmtT(val: number): string {
  if (val >= 1_000_000_000_000) return `${(val / 1_000_000_000_000).toFixed(2)}T`;
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(0)}M`;
  return val.toLocaleString();
}

/* ─────────────────────── active-slice renderer ─────────────────────── */

function renderActiveShape(props: any) {
  const {
    cx,
    cy,
    innerRadius,
    outerRadius,
    startAngle,
    endAngle,
    fill,
  } = props;
  return (
    <g>
      {/* Subtle outward lift — only 3px, with a soft shadow below */}
      <Sector
        cx={cx}
        cy={cy}
        innerRadius={innerRadius}
        outerRadius={outerRadius + 3}
        startAngle={startAngle}
        endAngle={endAngle}
        fill={fill}
        style={{ filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.15))' }}
      />
    </g>
  );
}

/* ───────────────────────────── main component ──────────────────────────── */

export default function LenderTreemap({ categories, totalOutstanding }: LenderTreemapProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [hoverSlice, setHoverSlice] = useState<string | null>(null);

  const filtered = useMemo(
    () =>
      categories
        .filter((c) => c.outstanding > 0)
        .sort((a, b) => b.outstanding - a.outstanding),
    [categories]
  );

  const external = filtered.filter((c) => isExternal(c.category));
  const domestic = filtered.filter(
    (c) => !isExternal(c.category) && isDomestic(c.category)
  );
  const other = filtered.filter(
    (c) => !isExternal(c.category) && !isDomestic(c.category)
  );

  const externalSum = external.reduce((s, c) => s + c.outstanding, 0);
  const domesticSum = domestic.reduce((s, c) => s + c.outstanding, 0);
  const otherSum = other.reduce((s, c) => s + c.outstanding, 0);
  const externalShare = totalOutstanding > 0 ? (externalSum / totalOutstanding) * 100 : 0;
  const domesticShare = totalOutstanding > 0 ? (domesticSum / totalOutstanding) * 100 : 0;

  const outerData = useMemo(
    () =>
      [
        { name: 'External', value: externalSum, color: '#C94A4A', share: externalShare },
        { name: 'Domestic', value: domesticSum, color: '#4A7C5C', share: domesticShare },
        otherSum > 0
          ? {
              name: 'Other',
              value: otherSum,
              color: '#D9A441',
              share: totalOutstanding > 0 ? (otherSum / totalOutstanding) * 100 : 0,
            }
          : null,
      ].filter(Boolean) as Array<{ name: string; value: number; color: string; share: number }>,
    [externalSum, domesticSum, otherSum, externalShare, domesticShare, totalOutstanding]
  );

  const innerData = useMemo(
    () =>
      filtered.map((c) => {
        const pal = paletteFor(c.category);
        return {
          name: c.label,
          value: c.outstanding,
          color: pal.base,
          gradientStart: pal.start,
          gradientEnd: pal.end,
          category: c.category,
          share: c.share,
        };
      }),
    [filtered]
  );

  /* Center readout: reflects the slice being hovered/clicked, else default.
     Lookup order — outer ring (External/Domestic/Other) → inner ring
     (per-category label) → drill-down card label → fallback to total. */
  const centerInfo = useMemo(() => {
    const def = {
      eyebrow: 'Total owed',
      value: `KES ${fmtT(totalOutstanding)}`,
      caption: `${filtered.length} categories`,
      accent: '#1B3A2A',
    };
    if (!hoverSlice) return def;
    const outer = outerData.find((d) => d.name === hoverSlice);
    if (outer) {
      return {
        eyebrow: outer.name,
        value: `KES ${fmtT(outer.value)}`,
        caption: `${outer.share.toFixed(1)}% of total`,
        accent: outer.color,
      };
    }
    const inner = innerData.find((d) => d.name === hoverSlice);
    if (inner) {
      return {
        eyebrow: inner.name,
        value: `KES ${fmtT(inner.value)}`,
        caption: `${inner.share.toFixed(1)}% of total`,
        accent: inner.color,
      };
    }
    // Drill-down cards use category.label which mirrors innerData names,
    // so the previous branch should have caught it. Keep a defensive fallback.
    return def;
  }, [hoverSlice, outerData, innerData, totalOutstanding, filtered.length]);

  if (!filtered.length) {
    return (
      <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 p-8 text-center text-sm text-neutral-muted'>
        No lender breakdown available yet.
      </div>
    );
  }

  return (
    <div className='space-y-5'>
      {/* ── Split summary: External vs Domestic ── */}
      <div className='grid grid-cols-1 sm:grid-cols-2 gap-3'>
        <motion.div
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
          onMouseEnter={() => setHoverSlice('External')}
          onMouseLeave={() => setHoverSlice(null)}
          className='relative rounded-2xl bg-white dark:bg-surface-base border border-gov-copper/25 shadow-surface p-5 overflow-hidden cursor-default'>
          <div className='absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-gov-copper via-gov-copper/70 to-gov-copper/30' />
          <div className='flex items-center justify-between mb-2'>
            <span className='text-[11px] font-semibold uppercase tracking-[0.15em] text-gov-copper'>
              External debt
            </span>
            <span className='text-sm font-bold text-gov-copper tabular-nums bg-gov-copper/10 px-2 py-0.5 rounded-full'>
              {externalShare.toFixed(1)}%
            </span>
          </div>
          <div className='text-3xl font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight'>
            KES {fmtT(externalSum)}
          </div>
          <p className='text-[11px] text-neutral-muted mt-2 leading-relaxed'>
            Foreign-currency exposure — World Bank, China Exim, Eurobonds. FX risk on the shilling.
          </p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
          onMouseEnter={() => setHoverSlice('Domestic')}
          onMouseLeave={() => setHoverSlice(null)}
          className='relative rounded-2xl bg-white dark:bg-surface-base border border-gov-sage/25 shadow-surface p-5 overflow-hidden cursor-default'>
          <div className='absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-gov-sage via-gov-sage/70 to-gov-sage/30' />
          <div className='flex items-center justify-between mb-2'>
            <span className='text-[11px] font-semibold uppercase tracking-[0.15em] text-gov-sage'>
              Domestic debt
            </span>
            <span className='text-sm font-bold text-gov-sage tabular-nums bg-gov-sage/10 px-2 py-0.5 rounded-full'>
              {domesticShare.toFixed(1)}%
            </span>
          </div>
          <div className='text-3xl font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight'>
            KES {fmtT(domesticSum)}
          </div>
          <p className='text-[11px] text-neutral-muted mt-2 leading-relaxed'>
            Treasury Bonds &amp; Bills held in-country by banks &amp; pension funds. Rate risk.
          </p>
        </motion.div>
      </div>

      {/* ── Hero: concentric donut + flow bar ── */}
      <div className='rounded-2xl bg-gradient-to-br from-white via-gov-sand/30 to-white dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated border border-neutral-border/40 shadow-surface p-5 sm:p-7'>
        <div className='grid grid-cols-1 lg:grid-cols-5 gap-6 items-center'>
          {/* Donut */}
          <div className='lg:col-span-2 relative'>
            <div className='relative w-full h-[340px] sm:h-[360px]'>
              <ResponsiveContainer width='100%' height='100%'>
                <PieChart>
                  <defs>
                    {/* Radial gradients for each inner slice — subtle tonal depth
                        rather than flashy light-to-dark. Centered brighter stop
                        gives the slice a soft inner glow without flattening. */}
                    {innerData.map((d, i) => (
                      <radialGradient
                        key={`grad-${i}`}
                        id={`donut-grad-${i}`}
                        cx='50%'
                        cy='50%'
                        r='75%'
                        fx='40%'
                        fy='40%'>
                        <stop offset='0%' stopColor={d.gradientStart} stopOpacity={1} />
                        <stop offset='100%' stopColor={d.gradientEnd} stopOpacity={1} />
                      </radialGradient>
                    ))}
                    {/* Outer ring gradients — deeper, near-solid tones */}
                    <radialGradient
                      id='donut-outer-ext'
                      cx='50%'
                      cy='50%'
                      r='75%'
                      fx='40%'
                      fy='40%'>
                      <stop offset='0%' stopColor='#B83E3E' stopOpacity={1} />
                      <stop offset='100%' stopColor='#7A2626' stopOpacity={1} />
                    </radialGradient>
                    <radialGradient
                      id='donut-outer-dom'
                      cx='50%'
                      cy='50%'
                      r='75%'
                      fx='40%'
                      fy='40%'>
                      <stop offset='0%' stopColor='#3B7251' stopOpacity={1} />
                      <stop offset='100%' stopColor='#1F4A30' stopOpacity={1} />
                    </radialGradient>
                    <radialGradient
                      id='donut-outer-other'
                      cx='50%'
                      cy='50%'
                      r='75%'
                      fx='40%'
                      fy='40%'>
                      <stop offset='0%' stopColor='#B38628' stopOpacity={1} />
                      <stop offset='100%' stopColor='#7D591A' stopOpacity={1} />
                    </radialGradient>
                    {/* Soft ambient drop shadow behind the whole donut */}
                    <filter id='donut-shadow' x='-20%' y='-20%' width='140%' height='140%'>
                      <feDropShadow
                        dx='0'
                        dy='1'
                        stdDeviation='2.5'
                        floodColor='#1B3A2A'
                        floodOpacity='0.18'
                      />
                    </filter>
                  </defs>
                  {/* Inner ring — categories (thinner, refined) */}
                  <Pie
                    data={innerData}
                    dataKey='value'
                    cx='50%'
                    cy='50%'
                    innerRadius={74}
                    outerRadius={100}
                    paddingAngle={0.8}
                    cornerRadius={3}
                    startAngle={90}
                    endAngle={-270}
                    stroke='#FAF7F2'
                    strokeWidth={1}
                    activeIndex={
                      hoverSlice
                        ? innerData.findIndex((d) => d.name === hoverSlice)
                        : -1
                    }
                    activeShape={renderActiveShape}
                    onMouseEnter={(_, idx) =>
                      setHoverSlice(innerData[idx]?.name || null)
                    }
                    onMouseLeave={() => setHoverSlice(null)}
                    isAnimationActive={true}
                    animationDuration={900}>
                    {innerData.map((_, idx) => (
                      <Cell
                        key={`inner-${idx}`}
                        fill={`url(#donut-grad-${idx})`}
                      />
                    ))}
                  </Pie>
                  {/* Outer ring — External / Domestic / Other (refined stroke) */}
                  <Pie
                    data={outerData}
                    dataKey='value'
                    cx='50%'
                    cy='50%'
                    innerRadius={107}
                    outerRadius={138}
                    paddingAngle={0.6}
                    cornerRadius={4}
                    startAngle={90}
                    endAngle={-270}
                    stroke='#FAF7F2'
                    strokeWidth={1.5}
                    activeIndex={
                      hoverSlice
                        ? outerData.findIndex((d) => d.name === hoverSlice)
                        : -1
                    }
                    activeShape={renderActiveShape}
                    onMouseEnter={(_, idx) =>
                      setHoverSlice(outerData[idx]?.name || null)
                    }
                    onMouseLeave={() => setHoverSlice(null)}
                    isAnimationActive={true}
                    animationDuration={1100}>
                    {outerData.map((d) => (
                      <Cell
                        key={`outer-${d.name}`}
                        fill={
                          d.name === 'External'
                            ? 'url(#donut-outer-ext)'
                            : d.name === 'Domestic'
                              ? 'url(#donut-outer-dom)'
                              : 'url(#donut-outer-other)'
                        }
                      />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              {/* Center readout — constrained width so long labels never spill
                  past the inner hole. Inner radius is 74px → 148px diameter;
                  we clamp the text container to 130px to leave visual margin. */}
              <div className='absolute inset-0 flex items-center justify-center pointer-events-none'>
                <motion.div
                  key={centerInfo.eyebrow + centerInfo.value}
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                  className='text-center'
                  style={{ maxWidth: '130px' }}>
                  <div
                    className='text-[9px] uppercase tracking-[0.18em] font-semibold truncate'
                    style={{ color: centerInfo.accent, opacity: 0.85 }}>
                    {centerInfo.eyebrow}
                  </div>
                  <div className='text-[17px] sm:text-[19px] font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight mt-0.5 leading-none'>
                    {centerInfo.value}
                  </div>
                  <div className='text-[9.5px] text-neutral-muted mt-1.5 leading-tight'>
                    {centerInfo.caption}
                  </div>
                </motion.div>
              </div>
            </div>
          </div>

          {/* Flow bar + legend column */}
          <div className='lg:col-span-3 space-y-4'>
            <div>
              <div className='flex items-baseline justify-between mb-2'>
                <h4 className='text-sm font-semibold text-gov-dark dark:text-white'>
                  Breakdown by instrument
                </h4>
                <span className='text-[11px] text-neutral-muted'>
                  {filtered.length} categories
                </span>
              </div>
              {/* Flow bar */}
              <div className='relative w-full h-11 rounded-full overflow-hidden bg-gov-sand/60 border border-neutral-border/20 shadow-inner flex'>
                {innerData.map((d, i) => {
                  const pct = totalOutstanding > 0 ? (d.value / totalOutstanding) * 100 : 0;
                  if (pct < 0.1) return null;
                  const isHover = hoverSlice === d.name;
                  return (
                    <motion.div
                      key={d.category}
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{
                        duration: 0.9,
                        delay: 0.1 + i * 0.05,
                        ease: [0.22, 1, 0.36, 1],
                      }}
                      onMouseEnter={() => setHoverSlice(d.name)}
                      onMouseLeave={() => setHoverSlice(null)}
                      style={{
                        background: `linear-gradient(135deg, ${d.gradientStart}, ${d.gradientEnd})`,
                        filter: isHover ? 'brightness(1.1)' : 'brightness(1)',
                        transform: isHover ? 'scaleY(1.08)' : 'scaleY(1)',
                        transformOrigin: 'center',
                        transition: 'filter .2s, transform .2s',
                      }}
                      className='h-full relative group cursor-default'>
                      {pct > 8 && (
                        <span className='absolute inset-0 flex items-center justify-center px-2 text-[10px] font-bold text-white/95 drop-shadow-sm tabular-nums'>
                          {pct.toFixed(1)}%
                        </span>
                      )}
                    </motion.div>
                  );
                })}
              </div>
            </div>

            {/* Legend chips */}
            <div className='grid grid-cols-1 sm:grid-cols-2 gap-1.5'>
              {innerData.map((d) => {
                const isHover = hoverSlice === d.name;
                return (
                  <div
                    key={d.category}
                    onMouseEnter={() => setHoverSlice(d.name)}
                    onMouseLeave={() => setHoverSlice(null)}
                    className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition-all ${
                      isHover
                        ? 'bg-white dark:bg-surface-base shadow-sm border border-neutral-border/40'
                        : 'bg-transparent border border-transparent'
                    }`}>
                    <span
                      className='w-2.5 h-6 rounded-sm flex-shrink-0'
                      style={{
                        background: `linear-gradient(180deg, ${d.gradientStart}, ${d.gradientEnd})`,
                      }}
                    />
                    <div className='flex-1 min-w-0'>
                      <div className='flex items-baseline justify-between gap-2'>
                        <span className='text-[11px] font-semibold text-gov-dark dark:text-white truncate'>
                          {d.name}
                        </span>
                        <span className='text-[11px] font-bold tabular-nums text-gov-dark dark:text-white'>
                          {d.share.toFixed(1)}%
                        </span>
                      </div>
                      <div className='text-[10px] text-neutral-muted tabular-nums leading-tight'>
                        KES {fmtT(d.value)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── Lender drill-down grid ── */}
      <div>
        <h4 className='text-sm font-semibold text-gov-dark dark:text-white mb-2'>
          Who each category is owed to
        </h4>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5'>
          {filtered.map((cat) => {
            const pal = paletteFor(cat.category);
            const isOpen = expanded === cat.category;
            const lenders = cat.lenders || [];
            const hasLenders = lenders.length > 0;
            const topLender = lenders[0];
            return (
              <motion.div
                key={cat.category}
                layout
                onMouseEnter={() => setHoverSlice(cat.label)}
                onMouseLeave={() => setHoverSlice(null)}
                className={`relative rounded-xl bg-white dark:bg-surface-base border shadow-sm overflow-hidden transition-shadow ${
                  isOpen ? 'shadow-elevated' : 'hover:shadow-md'
                } ${hoverSlice === cat.label ? 'ring-2 ring-offset-1 ring-offset-gov-sand' : ''}`}
                style={{
                  borderColor: isOpen ? pal.base : 'rgba(0,0,0,0.06)',
                  ...(hoverSlice === cat.label ? { boxShadow: `0 0 0 2px ${pal.base}55` } : {}),
                }}>
                {/* Accent stripe on the left */}
                <div
                  className='absolute left-0 top-0 bottom-0 w-1'
                  style={{
                    background: `linear-gradient(180deg, ${pal.start}, ${pal.end})`,
                  }}
                />
                <button
                  type='button'
                  onClick={() =>
                    hasLenders && setExpanded(isOpen ? null : cat.category)
                  }
                  className={`w-full text-left pl-4 pr-3 py-3 flex items-start gap-3 ${
                    hasLenders ? 'cursor-pointer' : 'cursor-default'
                  }`}>
                  <div className='flex-1 min-w-0'>
                    <div className='flex items-baseline justify-between gap-2 mb-0.5'>
                      <span className='text-xs font-semibold text-gov-dark dark:text-white truncate'>
                        {cat.label}
                      </span>
                      <span
                        className='text-[11px] font-bold tabular-nums'
                        style={{ color: pal.base }}>
                        {cat.share.toFixed(1)}%
                      </span>
                    </div>
                    <div className='text-sm font-bold text-gov-dark dark:text-white tabular-nums'>
                      KES {fmtT(cat.outstanding)}
                    </div>
                    {/* Mini bar showing share of total */}
                    <div className='mt-2 h-1 w-full rounded-full bg-neutral-border/30 overflow-hidden'>
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(100, cat.share)}%` }}
                        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                        className='h-full rounded-full'
                        style={{
                          background: `linear-gradient(90deg, ${pal.start}, ${pal.end})`,
                        }}
                      />
                    </div>
                    {topLender && !isOpen && (
                      <div className='mt-2 text-[10px] text-neutral-muted truncate'>
                        Top: <span className='font-medium text-gov-dark dark:text-white'>{topLender.lender}</span>
                      </div>
                    )}
                  </div>
                  {hasLenders && (
                    <motion.div
                      animate={{ rotate: isOpen ? 90 : 0 }}
                      transition={{ duration: 0.2 }}
                      className='flex-shrink-0 mt-0.5'>
                      <ChevronRight size={14} className='text-neutral-muted' />
                    </motion.div>
                  )}
                </button>
                {isOpen && hasLenders && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className='px-4 pb-3 pl-4 border-t border-neutral-border/20 space-y-1.5 pt-2.5'>
                    {lenders.slice(0, 8).map((l) => {
                      const pct =
                        cat.outstanding > 0 ? (l.outstanding / cat.outstanding) * 100 : 0;
                      return (
                        <div key={l.lender}>
                          <div className='flex justify-between items-baseline gap-2 text-[11px]'>
                            <span className='text-neutral-muted truncate'>{l.lender}</span>
                            <span className='text-gov-dark dark:text-white font-semibold tabular-nums flex-shrink-0'>
                              {fmtT(l.outstanding)}
                            </span>
                          </div>
                          <div className='mt-1 h-[3px] w-full rounded-full bg-neutral-border/20 overflow-hidden'>
                            <div
                              className='h-full rounded-full'
                              style={{
                                width: `${Math.max(2, Math.min(100, pct))}%`,
                                background: `linear-gradient(90deg, ${pal.start}, ${pal.end})`,
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </motion.div>
                )}
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
