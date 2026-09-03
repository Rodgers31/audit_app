/**
 * Plain-English glossary — search + filter + grouped accordion.
 *
 * Self-contained: no card-in-card wrapper, no per-term animation gimmicks,
 * no dynamically-constructed Tailwind classes. Every term rolls up to a
 * category section; expanding a row reveals the long explanation, a
 * handful of Kenyan examples, and (when it exists) a deep link to the
 * constitutional article that anchors the term.
 */
'use client';

import {
  filterTerms,
  GLOSSARY_CATEGORIES,
  getCategoryCounts,
  type GlossaryExample,
  glossaryTerms,
  groupByCategory,
  type GlossaryCategoryId,
} from '@/data/glossaryTerms';
import { type CivicFigure, type CivicFigureKey, getCivicFigures } from '@/lib/api/civic';
import { formatKesWords } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, ScrollText, Search } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

type CivicFigures = Partial<Record<CivicFigureKey, CivicFigure>>;

/**
 * Render a glossary example. Static strings pass through; live examples get
 * the current figure substituted in. When a figure was never seeded or the
 * API is unavailable, we fall back to the dated historical sentence — never a
 * fabricated current number (DESIGN §1: last-known-good, dated).
 */
function renderExample(ex: GlossaryExample, figures?: CivicFigures): string {
  if (typeof ex === 'string') return ex;
  const fig = figures?.[ex.figure];
  if (!fig?.available || fig.value == null || !fig.period) return ex.fallback;
  return ex.template
    .replace('{value}', formatKesWords(fig.value))
    .replace('{period}', fig.period);
}

interface InteractiveGlossaryProps {
  /** Optional externally-controlled search term. */
  searchTerm?: string;
}

export default function InteractiveGlossary({
  searchTerm = '',
}: InteractiveGlossaryProps) {
  const [internalSearch, setInternalSearch] = useState<string>('');
  const [category, setCategory] = useState<GlossaryCategoryId | 'all'>('all');
  const [openId, setOpenId] = useState<string | null>(null);

  // Live civic figures (GDP, budget, debt, equitable share) for examples.
  // On error/loading we simply render the dated fallbacks baked into each term.
  const { data: civic } = useQuery({
    queryKey: ['civic-figures'],
    queryFn: getCivicFigures,
    staleTime: 1000 * 60 * 60, // 1h — these change at most a few times a year
  });
  const figures = civic?.figures;

  const searchValue = searchTerm || internalSearch;
  const counts = useMemo(() => getCategoryCounts(), []);
  const filtered = useMemo(
    () => filterTerms(glossaryTerms, searchValue, category),
    [searchValue, category]
  );
  const grouped = useMemo(() => groupByCategory(filtered), [filtered]);
  const totalMatches = filtered.length;

  return (
    <div className='space-y-5'>
      {/* ── Toolbar ── */}
      <div className='sticky top-[64px] z-10 flex flex-col gap-3 rounded-2xl border border-white/60 bg-white/85 p-3 shadow-surface backdrop-blur-md sm:p-4'>
        {!searchTerm && (
          <label className='relative block'>
            <span className='sr-only'>Search glossary</span>
            <Search
              size={15}
              className='pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-neutral-muted'
            />
            <input
              type='search'
              value={internalSearch}
              onChange={(e) => setInternalSearch(e.target.value)}
              placeholder='Search terms, examples, or definitions…'
              className='w-full rounded-xl border border-neutral-border bg-white/80 dark:bg-surface-elevated py-2.5 pl-9 pr-3 text-sm shadow-inner transition-shadow placeholder:text-neutral-muted focus:outline-none focus:ring-2 focus:ring-gov-sage/40'
            />
          </label>
        )}

        <div className='flex flex-wrap items-center gap-2'>
          {GLOSSARY_CATEGORIES.map((cat) => {
            const isActive = cat.id === category;
            const count = counts[cat.id] ?? 0;
            if (cat.id !== 'all' && count === 0) return null;
            return (
              <button
                key={cat.id}
                type='button'
                onClick={() => setCategory(cat.id)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition-colors ${
                  isActive
                    ? 'bg-gov-forest text-white shadow-surface'
                    : 'bg-gov-forest/5 text-gov-forest dark:text-emerald-100 hover:bg-gov-forest/10'
                }`}>
                {cat.label}
                <span
                  className={`rounded-full px-1.5 text-[11px] ${
                    isActive ? 'bg-white/20 text-white' : 'bg-white dark:bg-surface-base text-gov-forest/70 dark:text-emerald-100/70'
                  }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div className='flex items-center justify-between text-[11px] text-neutral-muted'>
          <span>
            {searchValue ? (
              <>Showing <strong className='text-gov-dark dark:text-white'>{totalMatches}</strong> {totalMatches === 1 ? 'term' : 'terms'} for &ldquo;{searchValue}&rdquo;</>
            ) : (
              <>
                <strong className='text-gov-dark dark:text-white'>{glossaryTerms.length}</strong> terms across {GLOSSARY_CATEGORIES.length - 1} themes
              </>
            )}
          </span>
          {(searchValue || category !== 'all') && (
            <button
              type='button'
              onClick={() => {
                setInternalSearch('');
                setCategory('all');
              }}
              className='font-semibold text-gov-forest dark:text-emerald-100 hover:underline'>
              Reset filters
            </button>
          )}
        </div>
      </div>

      {/* ── Grouped sections ── */}
      {grouped.length === 0 ? (
        <div className='rounded-2xl border border-dashed border-neutral-border bg-white/60 dark:bg-surface-elevated p-10 text-center'>
          <Search size={28} className='mx-auto mb-3 text-neutral-muted' />
          <h3 className='font-display text-lg text-gov-dark dark:text-white'>No matches</h3>
          <p className='mt-1 text-sm text-neutral-muted'>
            Try a simpler word, or reset the filters above.
          </p>
        </div>
      ) : (
        grouped.map((group) => (
          <section
            key={group.category.id}
            aria-labelledby={`glossary-${group.category.id}`}
            className='space-y-2'>
            <div className='flex flex-wrap items-end justify-between gap-2 border-b border-neutral-border/60 pb-2'>
              <div>
                <h3
                  id={`glossary-${group.category.id}`}
                  className='font-display text-lg text-gov-dark dark:text-white sm:text-xl'>
                  {group.category.label}
                </h3>
                <p className='text-[13px] text-neutral-muted'>{group.category.blurb}</p>
              </div>
              <span className='text-[11px] font-semibold uppercase tracking-wider text-gov-forest/60 dark:text-emerald-100/60'>
                {group.terms.length} {group.terms.length === 1 ? 'term' : 'terms'}
              </span>
            </div>

            <ul className='divide-y divide-neutral-border/60 overflow-hidden rounded-2xl border border-white/70 bg-white/70 dark:bg-surface-elevated shadow-surface'>
              {group.terms.map((term) => {
                const Icon = term.icon;
                const isOpen = openId === term.id;
                return (
                  <li key={term.id}>
                    <button
                      type='button'
                      onClick={() => setOpenId((v) => (v === term.id ? null : term.id))}
                      aria-expanded={isOpen}
                      className={`flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-gov-cream/40 dark:bg-surface-sunken sm:px-5 sm:py-4 ${
                        isOpen ? 'bg-gov-cream/50 dark:bg-surface-sunken' : ''
                      }`}>
                      <span className='mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gov-forest/8 text-gov-forest dark:text-emerald-100'>
                        <Icon size={16} />
                      </span>
                      <span className='min-w-0 flex-1'>
                        <span className='flex flex-wrap items-center gap-1.5'>
                          <span className='font-display text-[15.5px] font-semibold text-gov-dark dark:text-white'>
                            {term.term}
                          </span>
                          {term.abbreviation && (
                            <span className='rounded-md bg-gov-forest/10 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-gov-forest dark:text-emerald-100'>
                              {term.abbreviation}
                            </span>
                          )}
                        </span>
                        <span className='mt-0.5 block text-[13.5px] leading-snug text-neutral-text'>
                          {term.shortDef}
                        </span>
                      </span>
                      <motion.span
                        animate={{ rotate: isOpen ? 180 : 0 }}
                        transition={{ duration: 0.2 }}
                        className='mt-1 shrink-0 text-neutral-muted'>
                        <ChevronDown size={16} />
                      </motion.span>
                    </button>

                    <AnimatePresence initial={false}>
                      {isOpen && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                          className='overflow-hidden'>
                          <div className='space-y-4 border-t border-neutral-border/60 bg-gov-cream/30 dark:bg-surface-sunken px-4 py-4 sm:px-5 sm:py-5'>
                            <p className='text-[14px] leading-relaxed text-gov-dark dark:text-white'>
                              {term.longDef}
                            </p>
                            <div>
                              <div className='mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-gov-forest/70 dark:text-emerald-100/70'>
                                In plain life
                              </div>
                              <ul className='space-y-1.5'>
                                {term.examples.map((ex, i) => (
                                  <li
                                    key={i}
                                    className='flex items-start gap-2 text-[13.5px] leading-relaxed text-neutral-text'>
                                    <span className='mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-gov-gold' />
                                    <span>{renderExample(ex, figures)}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                            {term.relatedArticle && (
                              <Link
                                href={`/learn#constitution-book`}
                                className='inline-flex items-center gap-2 rounded-lg bg-gov-forest/10 px-3 py-2 text-[12.5px] font-semibold text-gov-forest dark:text-emerald-100 transition-colors hover:bg-gov-forest/15'>
                                <ScrollText size={13} />
                                {term.relatedArticle.label}
                              </Link>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
