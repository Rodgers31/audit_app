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
  /** What the figure is — see BASIS_LABEL. Absent means nothing was recorded. */
  basis?: string | null;
  /** The row's own note explaining the figure, e.g. how it was derived. */
  basis_note?: string | null;
}

/* ─── Provenance ───────────────────────────────────────────────────────────

   Two of the six heads on this page are not figures KRA published:

   * `Other Tax Revenue` is a subtraction — the exchequer total less the heads
     KRA names — in every year with actuals;
   * the whole of FY 2022/23 is back-computed out of the FY 2023/24 release's
     growth rates, and it is the leftmost bar of every sparkline below.

   They rendered as equals under one "Source: KRA Annual Performance" credit.
   The rows always knew better; the API now carries `basis` so the page can
   say so where the reader is looking. An absent basis is treated as absence —
   it earns no badge, and it earns no credit either.

   The headline "How KRA collected KES …" stays unqualified on purpose: KRA
   does publish the exchequer total, and does collect the taxes in the
   residual. What is unpublished is the per-head split, which is what the
   cards and the footnote below are about.                                  */
const BASIS_LABEL: Record<string, string> = {
  derived: 'Derived',
  residual: 'Residual',
  projected: 'Projected',
};

/** True for a figure the cited source states for that year. */
const isPublished = (basis?: string | null) => basis === 'published';

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
  // `Other Tax Revenue` deliberately has no blurb here. It used to read
  // "Stamp duty, agricultural cess, minor taxes lumped together", which named
  // a cess the row does not cover and read as a measured stream. It is a
  // residual, and its own note says what it absorbs — so the note is what the
  // card shows. See descriptionFor.
};

/** Strip the prefix the badge beside it already carries. */
function trimBasisPrefix(note: string): string {
  return note.replace(/^(Derived|Residual|Projected)\s*:\s*/i, '');
}

/**
 * What the card says the figure is.
 *
 * A row that declares itself unpublished gets its own note, because for those
 * the interesting fact is not what the tax is but where the number came from —
 * and because the generic blurb was wrong for the one row that most needed it
 * to be right. Everything else gets the editorial one-liner.
 *
 * The `basis == null` case is deliberately *not* treated as unpublished. Rows
 * seeded before `basis` existed still carry `notes`, and swapping the blurb for
 * one of those prints "KRA Annual Performance FY 2024/25: PAYE collected KES
 * 560.963B" as the card's description — putting the sourcing claim this change
 * removes straight back on the page, through a field meant to describe the tax.
 */
function descriptionFor(source: { revenue_type: string; basis?: string | null; basis_note?: string | null }): string {
  const declaredUnpublished = source.basis != null && !isPublished(source.basis);
  if (declaredUnpublished && source.basis_note) {
    return trimBasisPrefix(source.basis_note);
  }
  return SOURCE_DESC[source.revenue_type] ?? '';
}

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
      // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- sort comparator
      .sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0));
    // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- reducer accumulator
    const totalB = list.reduce((s, r) => s + (r.amount ?? 0), 0);

    // 3-year series per source for the sparkline
    const seriesFYs = multiSourceActualFYs.slice(-3);

    return list.map((r) => {
      const pal = paletteFor(r.revenue_type);
      const series = seriesFYs
        .map((fy) => {
          const row = (fy.sources ?? []).find((s) => s.revenue_type === r.revenue_type);
          return {
            year: fy.fiscal_year?.replace('FY ', '') ?? '',
            amount: row?.amount ?? null,
            // Carried per point: one stream can be published in the latest
            // year and back-computed in the earliest, which is exactly the
            // FY 2022/23 case these bars would otherwise hide.
            basis: row?.basis ?? null,
          };
        })
        .filter((p) => p.amount != null && p.amount > 0) as {
        year: string;
        amount: number;
        basis: string | null;
      }[];
      const prevVal = prev?.sources?.find((s) => s.revenue_type === r.revenue_type)?.amount ?? null;
      const yoy =
        prevVal != null && prevVal > 0 && r.amount != null
          ? ((r.amount - prevVal) / prevVal) * 100
          : null;
      return {
        key: r.revenue_type,
        label: r.revenue_type,
        // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- the caller filters to fiscal years whose streams all carry amounts, so a null here is unreachable
        amount: r.amount ?? 0,
        // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- see above — share is computed from the same filtered set
        share: totalB > 0 ? ((r.amount ?? 0) / totalB) * 100 : 0,
        yoy,
        pal,
        desc: descriptionFor(r),
        basis: r.basis ?? null,
        series,
        totalB,
      };
    });
  }, [latest, prev, multiSourceActualFYs]);

  /* ── What the section may claim about its source ──────────────────────
     Built from the rows on screen rather than hardcoded, so the credit
     cannot outlive the data it describes. Three outcomes:
       - nothing declared  → no credit at all (absence is not a claim);
       - everything published → the plain KRA credit;
       - anything else     → the credit, qualified, with the specifics on
                             each card and in the footnote below.            */
  const provenance = useMemo(() => {
    const cardBases = rows.map((r) => r.basis);
    // A charted year is called out when a stream KRA publishes today carries a
    // figure KRA did not publish back then — the FY 2022/23 sparkline bars.
    // Rows that are unpublished in their own right are labelled on their card
    // instead, so they do not also drag their whole series into the footnote.
    const flaggedYears: Record<string, string[]> = {};
    for (const r of rows) {
      if (!isPublished(r.basis)) continue;
      for (const p of r.series) {
        if (p.basis && !isPublished(p.basis)) {
          const seen = flaggedYears[p.year] ?? (flaggedYears[p.year] = []);
          if (!seen.includes(p.basis)) seen.push(p.basis);
        }
      }
    }
    const anyFlaggedYear = Object.keys(flaggedYears).length > 0;
    const declared = cardBases.some((b) => b != null) || anyFlaggedYear;
    const unpublished =
      cardBases.some((b) => b != null && !isPublished(b)) || anyFlaggedYear;
    return { declared, unpublished, flaggedYears };
  }, [rows]);

  const basisFootnote = useMemo(() => {
    const years = Object.keys(provenance.flaggedYears).sort();
    if (years.length === 0) return null;
    const words = years
      .flatMap((y) => provenance.flaggedYears[y])
      .map((b) => BASIS_LABEL[b]?.toLowerCase() ?? b)
      .filter((w, i, all) => all.indexOf(w) === i)
      .sort();
    const yearList =
      years.length === 1
        ? years[0]
        : `${years.slice(0, -1).join(', ')} and ${years[years.length - 1]}`;
    return { yearList, plural: years.length > 1, words: words.join(' or ') };
  }, [provenance.flaggedYears]);

  if (!latest || rows.length === 0) return null;

  // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- guarded: `rows.length === 0` returns null on the line above, so rows[0] exists
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
        {provenance.declared && (
          <div className='text-right' data-testid='revenue-section-source'>
            <div className='text-[11px] uppercase tracking-wider font-semibold text-neutral-muted'>
              Source
            </div>
            <div className='text-[12px] font-semibold text-gov-dark dark:text-white'>
              KRA Annual Performance
              {provenance.unpublished && (
                <span className='font-normal text-neutral-muted'>
                  {' '}
                  — except where marked
                </span>
              )}
            </div>
            <div className='text-[11px] text-neutral-muted'>{latest.fiscal_year}</div>
          </div>
        )}
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
              data-revenue-card
              data-basis={r.basis ?? undefined}
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
                {/* A figure the source did not publish says so beside its own
                    number, not only in a note at the foot of the section. */}
                {!isPublished(r.basis) && BASIS_LABEL[r.basis ?? ''] && (
                  <span className='inline-block mb-1 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-amber-400/70 bg-amber-50 text-amber-800 dark:border-amber-600/50 dark:bg-amber-950/40 dark:text-amber-200'>
                    {BASIS_LABEL[r.basis ?? '']} — not a published line
                  </span>
                )}
                <div className='flex items-baseline justify-between gap-2'>
                  <div className='text-base font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight'>
                    KES {fmtB(r.amount)}
                  </div>
                  {r.yoy != null && (
                    <span
                      className={`inline-flex items-center gap-0.5 text-[11px] font-semibold px-1.5 py-0.5 rounded-full tabular-nums ${
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
                      // A bar is a quantity claim as much as a printed figure
                      // is. An unpublished year is drawn hollow so the reader
                      // can see which bars are not measurements.
                      const unpublished = p.basis != null && !isPublished(p.basis);
                      // The asterisk points at the footnote, so it goes only on
                      // bars the footnote covers: those the card's own badge
                      // does not already explain. On the residual card every
                      // bar is a residual and the badge says so — starring them
                      // would send the reader to a note about a different year.
                      const needsFootnote = unpublished && p.basis !== r.basis;
                      return (
                        <div
                          key={p.year}
                          className='flex-1 flex flex-col items-center gap-0.5'>
                          <div
                            data-testid='spark-bar'
                            data-year={p.year}
                            data-basis={p.basis ?? undefined}
                            title={
                              unpublished
                                ? `${p.year}: ${BASIS_LABEL[p.basis!] ?? p.basis} — not a published figure`
                                : undefined
                            }
                            className={`w-full rounded-t-sm transition-all ${
                              unpublished ? 'border border-dashed border-amber-500/70' : ''
                            }`}
                            style={{
                              height: `${Math.max(h, 10)}%`,
                              background: unpublished
                                ? 'transparent'
                                : isLatest
                                  ? `linear-gradient(180deg, ${r.pal.start}, ${r.pal.end})`
                                  : '#E2DDD5',
                            }}
                          />
                          <span
                            className={`text-[11px] tabular-nums ${
                              unpublished ? 'text-amber-700 dark:text-amber-300' : 'text-neutral-muted'
                            }`}>
                            {p.year}
                            {needsFootnote && '*'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {r.desc && (
                  <p className='mt-2 text-[11px] text-neutral-muted leading-snug'>
                    {r.desc}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Names the charted years whose bars are not measurements. The cards
          above label their own figure; this covers the sparkline, where a
          stream KRA publishes today carries a back-computed figure for an
          earlier year and nothing on the bar would otherwise say so. */}
      {basisFootnote && (
        <p
          data-testid='revenue-basis-footnote'
          className='mt-3 text-[11px] leading-snug text-neutral-muted'>
          <span aria-hidden='true'>* </span>
          {basisFootnote.plural ? 'The bars marked ' : 'The bar marked '}
          <strong className='font-semibold text-gov-dark dark:text-white'>
            {basisFootnote.yearList}
          </strong>{' '}
          {basisFootnote.plural ? 'are ' : 'is '}
          {basisFootnote.words} rather than published: KRA states the growth rate
          for that year, not the amount per tax head, so each head is
          back-computed from the following year&rsquo;s figure. Shown because the
          trend is real; marked because the level is not KRA&rsquo;s own.
        </p>
      )}
    </motion.section>
  );
}
