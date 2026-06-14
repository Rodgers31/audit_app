/**
 * LearnHero — the opening of the Learn hub.
 *
 * Search-forward layout: a single prominent search field with live
 * autocomplete. As the user types, matching articles appear in a
 * dropdown below — click one to jump straight to that article in
 * the Constitution book. If they'd rather see a ranked list in
 * context, the Enter key / Search button forwards the query to the
 * book's own search.
 *
 * The stat chips translate the scale of the content into a sentence.
 */
'use client';

import { CONSTITUTION_META, TOTAL_ARTICLES } from '@/data/constitution';
import { runSearch, type SearchHit } from '@/data/constitution/search';
import { warmSemanticIndex } from '@/data/constitution/semantic-search';
import { POPULAR_QUESTIONS } from '@/data/popularQuestions';
import { TOTAL_QUESTIONS } from '@/data/quizData';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowRight,
  BookOpen,
  Brain,
  ChevronRight,
  GraduationCap,
  HelpCircle,
  Loader2,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

interface LearnHeroProps {
  /** Forward the query to the Constitution book and scroll it into view. */
  onSearchSubmit: (query: string) => void;
  /** Jump directly to a specific article, picked from the autocomplete. */
  onArticleSelect: (chapterNumber: number, articleNumber: number) => void;
}

const EXAMPLE_QUERIES = ['Article 229', 'Auditor General', 'Chapter 6', 'Public debt', 'Devolution'];

export default function LearnHero({ onSearchSubmit, onArticleSelect }: LearnHeroProps) {
  const [value, setValue] = useState('');
  const [debounced, setDebounced] = useState('');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  /* ── Warm the semantic index once, in the background. The model is
     ~23MB quantized — download it after first paint so it's ready by
     the time the user finishes typing their first query. ── */
  useEffect(() => {
    const id = setTimeout(() => {
      warmSemanticIndex();
    }, 1200);
    return () => clearTimeout(id);
  }, []);

  /* ── Debounce ── */
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), 180);
    return () => clearTimeout(id);
  }, [value]);

  /* ── Run search when debounced value changes ── */
  useEffect(() => {
    const q = debounced.trim();
    if (q.length === 0) {
      setHits([]);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    runSearch(q, 7).then((res) => {
      if (cancelled) return;
      setHits(res.hits);
      setIsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  /* ── Close dropdown on outside click ── */
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  const submit = (q: string) => {
    const clean = q.trim();
    if (!clean) return;
    onSearchSubmit(clean);
    setOpen(false);
  };

  const pickHit = (h: SearchHit) => {
    onArticleSelect(h.chapter.number, h.article.number);
    setOpen(false);
  };

  const query = debounced.trim();
  const showDropdown = open && query.length > 0;
  const showHits = showDropdown && hits.length > 0;
  const showSearchAll = showDropdown && query.length >= 2;

  return (
    <section
      aria-labelledby='learn-hero-heading'
      className='relative rounded-3xl border border-white/60 text-white shadow-elevated'>
      {/* Clipped background layer — holds the gradient + decorative rings so the
          content layer above can overflow (e.g. the autocomplete dropdown). */}
      <div className='pointer-events-none absolute inset-0 overflow-hidden rounded-3xl bg-gradient-to-br from-gov-forest via-gov-dark to-gov-forest'>
        <div className='absolute -right-16 -top-16 h-64 w-64 rounded-full border border-white/10' />
        <div className='absolute -right-2 bottom-10 h-24 w-24 rounded-full border border-white/5' />
        <div className='absolute -left-12 -bottom-12 h-48 w-48 rounded-full bg-gov-gold/10 blur-2xl' />
      </div>

      <div className='relative grid gap-6 p-5 sm:p-8 lg:grid-cols-[1.3fr_1fr] lg:items-center lg:p-10'>
        {/* Left — copy + search */}
        <div className='min-w-0 max-w-2xl'>
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className='mb-4 inline-flex max-w-full items-center gap-2 overflow-hidden rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-gov-gold ring-1 ring-white/10 sm:tracking-widest'>
            <Sparkles size={12} className='shrink-0' />
            <span className='truncate'>Civic learning · plain-language explainers</span>
          </motion.div>

          <motion.h1
            id='learn-hero-heading'
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.05 }}
            className='font-display text-[1.75rem] leading-[1.12] text-white drop-shadow sm:text-4xl lg:text-[2.9rem]'>
            Understand Kenya&rsquo;s
            <span className='block text-gov-gold'>
              money, law &amp; power
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.12 }}
            className='mt-4 max-w-xl text-[15.5px] leading-relaxed text-white/80 sm:text-base'>
            Plain-language explainers, a searchable Constitution, and quick quizzes —
            all built from the same audited facts that power the rest of the dashboard.
          </motion.p>

          {/* Search — with live autocomplete */}
          <motion.div
            ref={wrapperRef}
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.2 }}
            className='relative mt-6 w-full max-w-xl'>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submit(value);
              }}
              className='flex items-center gap-2 rounded-2xl bg-white/95 p-1.5 shadow-elevated ring-1 ring-white/20'>
              <Search size={18} className='ml-3 text-gov-forest/70 dark:text-emerald-100/70' />
              <input
                ref={inputRef}
                type='search'
                value={value}
                onChange={(e) => {
                  setValue(e.target.value);
                  setOpen(true);
                }}
                onFocus={() => setOpen(true)}
                placeholder='Try "elections", "Article 229" or "public debt"…'
                className='min-w-0 flex-1 bg-transparent py-2.5 text-sm text-gov-dark dark:text-white outline-none placeholder:text-neutral-muted sm:text-[15px]'
                aria-label='Search civic topics or the Constitution'
                autoComplete='off'
              />
              {isLoading && (
                <Loader2 size={16} className='mr-2 shrink-0 animate-spin text-gov-forest/50 dark:text-emerald-100/50' />
              )}
              {value && !isLoading && (
                <button
                  type='button'
                  onClick={() => {
                    setValue('');
                    setDebounced('');
                    setHits([]);
                    inputRef.current?.focus();
                  }}
                  className='mr-1 rounded-full p-1 text-neutral-muted hover:bg-neutral-border/50 hover:text-gov-dark dark:text-white'
                  aria-label='Clear search'>
                  <X size={14} />
                </button>
              )}
              <button
                type='submit'
                className='inline-flex items-center gap-1.5 rounded-xl bg-gov-forest px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-gov-dark'>
                <span className='hidden sm:inline'>Search</span>
                <ArrowRight size={15} />
              </button>
            </form>

            {/* Autocomplete dropdown */}
            <AnimatePresence>
              {showDropdown && (showHits || showSearchAll) && (
                <motion.div
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.18 }}
                  className='absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-2xl border border-neutral-border bg-white dark:bg-surface-base text-gov-dark dark:text-white shadow-elevated'>
                  {showHits && (
                    <>
                      <div className='border-b border-neutral-border/60 px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-neutral-muted'>
                        Matching articles
                      </div>
                      <ul className='max-h-[320px] overflow-y-auto py-1'>
                        {hits.map((h, i) => (
                          <li key={`${h.chapter.number}-${h.article.number}-${i}`}>
                            <button
                              type='button'
                              onClick={() => pickHit(h)}
                              className='group flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-gov-forest/5'>
                              <span className='mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gov-gold/20 font-display text-sm font-bold text-gov-dark dark:text-white'>
                                {h.article.number}
                              </span>
                              <div className='min-w-0 flex-1'>
                                <div className='flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-gov-forest/70 dark:text-emerald-100/70'>
                                  <span>Ch {h.chapter.number}</span>
                                  <span>·</span>
                                  <span className='truncate text-neutral-muted normal-case tracking-normal'>
                                    {h.chapter.title}
                                  </span>
                                </div>
                                <div className='truncate text-sm font-semibold text-neutral-text'>
                                  {h.article.title}
                                </div>
                                {h.excerpt && (
                                  <div className='mt-0.5 line-clamp-2 text-[12px] text-neutral-muted'>
                                    {h.excerpt}
                                  </div>
                                )}
                              </div>
                              <ChevronRight
                                size={14}
                                className='mt-2 shrink-0 text-neutral-muted group-hover:text-gov-forest dark:text-emerald-100'
                              />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  {showSearchAll && (
                    <button
                      type='button'
                      onClick={() => submit(value)}
                      className='flex w-full items-center justify-between gap-3 border-t border-neutral-border/60 bg-gov-cream/40 dark:bg-surface-sunken px-3 py-2.5 text-left text-sm font-semibold text-gov-forest dark:text-emerald-100 transition-colors hover:bg-gov-forest/5'>
                      <span className='inline-flex items-center gap-2'>
                        <Search size={14} />
                        Search Constitution for &ldquo;{query}&rdquo;
                      </span>
                      <ArrowRight size={14} />
                    </button>
                  )}

                  {!showHits && showSearchAll && !isLoading && (
                    <div className='border-t border-neutral-border/60 px-3 py-2 text-[11.5px] text-neutral-muted'>
                      No direct matches — submit the search to browse in context.
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {/* Example chips */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className='mt-3 flex flex-wrap items-center gap-1.5 text-xs text-white/60'>
            <span>Try:</span>
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type='button'
                onClick={() => {
                  setValue(q);
                  submit(q);
                }}
                className='rounded-full bg-white/10 px-2.5 py-1 text-[11.5px] font-medium text-white/85 hover:bg-white/20'>
                {q}
              </button>
            ))}
          </motion.div>
        </div>

        {/* Right — stat cards */}
        <div className='grid min-w-0 grid-cols-2 gap-3 sm:gap-4'>
          <StatCard
            icon={BookOpen}
            value={CONSTITUTION_META.length}
            label='Chapters published'
            accent='text-gov-gold'
          />
          <StatCard
            icon={GraduationCap}
            value={TOTAL_ARTICLES}
            label='Articles to read'
            accent='text-white'
          />
          <StatCard
            icon={Brain}
            value={TOTAL_QUESTIONS}
            label='Quiz questions'
            accent='text-gov-gold'
          />
          <StatCard
            icon={HelpCircle}
            value={POPULAR_QUESTIONS.length}
            label='Popular Q&As'
            accent='text-white'
          />
        </div>
      </div>
    </section>
  );
}

function StatCard({
  icon: Icon,
  value,
  label,
  accent,
}: {
  icon: React.ElementType;
  value: number;
  label: string;
  accent: string;
}) {
  return (
    <motion.div
      whileHover={{ y: -3 }}
      className='rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur transition-colors hover:bg-white/15'>
      <Icon size={16} className={`mb-1.5 ${accent}`} />
      <div className={`font-display text-2xl font-bold ${accent}`}>{value}</div>
      <div className='text-[11px] text-white/70 sm:text-xs'>{label}</div>
    </motion.div>
  );
}
