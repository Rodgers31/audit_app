/**
 * ArticleViewer — renders one constitutional article as a "page" in the book.
 *
 * The parent passes a direction (1 for forward, -1 for back) and a unique key
 * so framer-motion's AnimatePresence can cross-fade with a page-turn feel.
 *
 * Search highlights are applied client-side via a simple non-regex token
 * substitution to keep the markup predictable for screen readers.
 */
'use client';

import type { ConstitutionArticle, ConstitutionChapter } from '@/data/constitution/types';
import { AnimatePresence, motion, type Variants } from 'framer-motion';
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  CheckCircle2,
  CornerDownLeft,
  Hash,
  Lightbulb,
  ScrollText,
} from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';

import { renderProse, type ReferenceTarget } from './prose';

/** Page-turn variants. `direction` is passed via AnimatePresence's custom prop. */
const PAGE_VARIANTS: Variants = {
  enter: (d: number) => ({ opacity: 0, x: d * 64, rotateY: d * -6 }),
  center: { opacity: 1, x: 0, rotateY: 0 },
  exit: (d: number) => ({ opacity: 0, x: d * -64, rotateY: d * 6 }),
};

interface ArticleViewerProps {
  chapter: ConstitutionChapter;
  article: ConstitutionArticle;
  /** Highlighted query, if any. */
  query?: string;
  /** +1 forward, -1 back — drives the slide direction. */
  direction: number;
  hasPrev: boolean;
  hasNext: boolean;
  prevLabel?: string;
  nextLabel?: string;
  onPrev: () => void;
  onNext: () => void;
  /** Next chapter in reading order, when we're on the last article. */
  nextChapterNumber?: number;
  nextChapterTitle?: string;
  onGoNextChapter?: () => void;
  /** Called when the reader clicks an "Article N" / "Chapter N"
   * reference embedded in the prose. The parent decides whether the
   * jump pushes history, opens in place, etc. */
  onReferenceClick?: (target: ReferenceTarget) => void;
  /** Label for the back-pill shown when the reader followed a
   * reference into this article. `null` / `undefined` hides it. */
  backTarget?: { articleNumber: number } | null;
  onBack?: () => void;
  /** Top-level clause the reader was pointed at — e.g. "3" when the
   * reference was "Article 144(3)(c)". On arrival we flash + scroll
   * to the paragraph whose leading "(X)" marker matches. `null` /
   * absent means "no clause highlight" (plain-article or non-
   * reference navigation: the page switch is itself the feedback). */
  highlightClause?: string | null;
}

/** Cheap, allocation-light highlight: splits on case-insensitive query. */
function highlight(text: string, query: string): React.ReactNode {
  if (!query || query.length < 2) return text;
  const q = query.trim();
  if (!q) return text;
  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  const out: React.ReactNode[] = [];
  let i = 0;
  let n = 0;
  while (i < text.length) {
    const j = lower.indexOf(needle, i);
    if (j === -1) {
      out.push(text.slice(i));
      break;
    }
    if (j > i) out.push(text.slice(i, j));
    out.push(
      <mark
        key={`h-${n++}`}
        className='rounded bg-gov-gold/30 px-0.5 text-gov-dark dark:text-white'>
        {text.slice(j, j + q.length)}
      </mark>
    );
    i = j + q.length;
  }
  return <>{out}</>;
}

export default function ArticleViewer({
  chapter,
  article,
  query = '',
  direction,
  hasPrev,
  hasNext,
  prevLabel,
  nextLabel,
  onPrev,
  onNext,
  nextChapterNumber,
  nextChapterTitle,
  onGoNextChapter,
  onReferenceClick,
  backTarget,
  onBack,
  highlightClause,
}: ArticleViewerProps) {
  const clauseRef = useRef<HTMLParagraphElement | null>(null);

  // When the viewer mounts with a clause to highlight, scroll that
  // paragraph into view inside the overflow-y-auto body. `block:
  // 'nearest'` (not 'start'): short articles where the whole body
  // already fits need no scroll, and 'start' would try to align the
  // paragraph with the viewport top — if the inner container can't
  // scroll the browser walks up ancestors and ends up scrolling the
  // outer page, visually pushing the article down. 'nearest' is a
  // no-op whenever the paragraph is already visible.
  useEffect(() => {
    if (!highlightClause || !clauseRef.current) return;
    clauseRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [article.number, highlightClause]);
  const pageKey = useMemo(
    () => `${chapter.number}-${article.number}`,
    [chapter.number, article.number]
  );
  const atEndOfChapter = !hasNext;
  const showNextChapter = atEndOfChapter && !!nextChapterNumber && !!onGoNextChapter;

  return (
    <div className='relative h-full' style={{ perspective: '1800px' }}>
      <AnimatePresence mode='wait' initial={false} custom={direction}>
        <motion.article
          key={pageKey}
          custom={direction}
          variants={PAGE_VARIANTS}
          initial='enter'
          animate='center'
          exit='exit'
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className='flex h-full flex-col'
          style={{ transformStyle: 'preserve-3d', transformOrigin: 'center' }}>
          {/* ── Header ── */}
          <header className='border-b border-neutral-border/70 px-5 pb-4 pt-5 sm:px-7 sm:pt-6'>
            {/* Back pill — only shown when the reader arrived here via an
                in-prose reference click. Sits above the chapter chip so it
                reads as "you followed a thread; here's how to unwind it"
                rather than general navigation (left/right arrows do that). */}
            {backTarget && onBack && (
              <button
                type='button'
                onClick={onBack}
                className='mb-3 inline-flex items-center gap-1.5 rounded-full border border-gov-forest/20 bg-gov-forest/5 px-3 py-1 text-[11px] font-semibold text-gov-forest dark:text-emerald-100 hover:bg-gov-forest/10 hover:border-gov-forest/40 transition-colors'>
                <CornerDownLeft size={12} />
                Back to Article {backTarget.articleNumber}
              </button>
            )}
            <div className='mb-2 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-gov-forest/70 dark:text-emerald-100/70'>
              <span className='inline-flex items-center gap-1 rounded-full bg-gov-forest/10 px-2 py-0.5 font-semibold'>
                <ScrollText size={11} />
                Chapter {chapter.number}
              </span>
              <span className='text-neutral-muted'>·</span>
              <span className='font-semibold text-neutral-muted'>{chapter.title}</span>
            </div>
            <div className='flex items-start gap-3'>
              <span className='shrink-0 rounded-xl bg-gov-gold/20 px-3 py-1.5 font-display text-xl font-bold text-gov-dark dark:text-white'>
                <Hash size={14} className='-mt-1 mr-0.5 inline text-gov-gold' />
                {article.number}
              </span>
              <h3 className='font-display text-2xl leading-tight text-gov-dark dark:text-white sm:text-[1.7rem]'>
                {highlight(article.title, query)}
              </h3>
            </div>
            {article.summary && (
              <p className='mt-3 rounded-xl border border-gov-sage/30 bg-gov-sage/10 px-3.5 py-2.5 text-[13.5px] leading-relaxed text-gov-forest dark:text-emerald-100'>
                <Bookmark size={13} className='-mt-0.5 mr-1 inline text-gov-sage' />
                {renderProse(article.summary, { query, onRefClick: onReferenceClick })}
              </p>
            )}
          </header>

          {/* ── Paragraphs ──
              No container-level flash anymore — only the paragraph
              whose leading "(X)" marker matches highlightClause
              flashes. That keeps the scope of the highlight aligned
              with the scope of the reference: "Article 144(3)" lights
              up clause (3), not the whole article. Paragraphs without
              a leading clause marker, or when highlightClause is
              absent, render unchanged. */}
          <div className='flex-1 space-y-3 overflow-y-auto px-5 py-5 text-[14.5px] leading-relaxed text-neutral-text sm:px-7 sm:py-6'>
            {article.paragraphs.map((p, i) => {
              const leading = /^\s*\((\w+)\)/.exec(p)?.[1];
              const isTarget = !!highlightClause && leading === highlightClause;
              return (
                <motion.p
                  key={i}
                  ref={isTarget ? clauseRef : undefined}
                  initial={isTarget ? { backgroundColor: 'rgb(254, 249, 195)' } : undefined}
                  animate={
                    isTarget
                      ? {
                          backgroundColor: [
                            'rgba(254, 249, 195, 1)',
                            'rgba(254, 249, 195, 1)',
                            'rgba(254, 249, 195, 0)',
                          ],
                        }
                      : undefined
                  }
                  transition={
                    isTarget
                      ? { duration: 2.4, times: [0, 0.25, 1], ease: 'easeOut' }
                      : undefined
                  }
                  className={`font-serif first-letter:text-[1.15em] first-letter:font-semibold ${
                    isTarget ? 'rounded-md px-2 -mx-2 py-1 -my-1' : ''
                  }`}>
                  {renderProse(p, { query, onRefClick: onReferenceClick })}
                </motion.p>
              );
            })}

            {article.explanation && (
              <div className='mt-4 rounded-xl bg-gradient-to-br from-gov-gold/15 via-gov-sand to-gov-cream/80 dark:from-gov-gold/[0.12] dark:via-surface-base dark:to-surface-elevated p-4 ring-1 ring-gov-gold/30 dark:ring-gov-gold/40'>
                <div className='mb-1 flex flex-wrap items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-gov-forest dark:text-emerald-100'>
                  <Lightbulb size={13} className='text-gov-gold' />
                  Why it matters
                  <span className='normal-case font-normal tracking-normal text-gov-dark/50 dark:text-white/50'>
                    · our plain-language take, not the law
                  </span>
                </div>
                <p className='text-[13.5px] leading-relaxed text-gov-dark dark:text-white'>
                  {renderProse(article.explanation, { query, onRefClick: onReferenceClick })}
                </p>
              </div>
            )}

            {article.tags && article.tags.length > 0 && (
              <div className='mt-3 flex flex-wrap gap-1.5 pt-2'>
                {article.tags.map((t) => (
                  <span
                    key={t}
                    className='rounded-full bg-gov-forest/5 px-2 py-0.5 text-[10.5px] font-medium text-gov-forest/70 dark:text-emerald-100/70'>
                    #{t}
                  </span>
                ))}
              </div>
            )}

            {showNextChapter && (
              <div className='mt-6 rounded-2xl border border-gov-forest/20 dark:border-gov-forest/40 bg-gradient-to-br from-gov-forest/5 via-white to-gov-sage/15 dark:from-gov-forest/[0.15] dark:via-surface-base dark:to-surface-elevated p-4 sm:p-5'>
                <div className='flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-gov-forest dark:text-emerald-100'>
                  <CheckCircle2 size={13} className='text-gov-sage' />
                  End of Chapter {chapter.number}
                </div>
                <div className='mt-2 flex flex-wrap items-center justify-between gap-3'>
                  <div className='min-w-0'>
                    <div className='text-[11px] font-semibold uppercase tracking-wider text-gov-forest/60 dark:text-emerald-100/60'>
                      Up next · Chapter {nextChapterNumber}
                    </div>
                    <div className='font-display text-base text-gov-dark dark:text-white sm:text-lg'>
                      {nextChapterTitle}
                    </div>
                  </div>
                  <button
                    type='button'
                    onClick={onGoNextChapter}
                    className='inline-flex shrink-0 items-center gap-2 rounded-xl bg-gov-forest px-4 py-2.5 text-sm font-semibold text-white shadow-surface transition-colors hover:bg-gov-dark'>
                    Read Chapter {nextChapterNumber}
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* ── Footer nav ── */}
          <footer className='flex items-center justify-between gap-3 border-t border-neutral-border/70 bg-gov-cream/60 dark:bg-surface-sunken px-5 py-3 sm:px-7'>
            <button
              type='button'
              onClick={onPrev}
              disabled={!hasPrev}
              className='inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-gov-forest dark:text-emerald-100 transition-colors hover:bg-gov-forest/10 disabled:cursor-not-allowed disabled:opacity-30'>
              <ArrowLeft size={16} />
              <span className='hidden sm:inline'>
                {prevLabel ? `Art. ${prevLabel}` : 'Previous'}
              </span>
              <span className='sm:hidden'>Prev</span>
            </button>
            <div className='text-[11px] font-semibold uppercase tracking-wider text-neutral-muted'>
              Article {article.number}
            </div>
            {showNextChapter ? (
              <button
                type='button'
                onClick={onGoNextChapter}
                className='inline-flex items-center gap-2 rounded-lg bg-gov-forest/10 px-3 py-2 text-sm font-semibold text-gov-forest dark:text-emerald-100 transition-colors hover:bg-gov-forest/20'>
                <span className='hidden sm:inline'>Ch. {nextChapterNumber}</span>
                <span className='sm:hidden'>Next ch.</span>
                <ArrowRight size={16} />
              </button>
            ) : (
              <button
                type='button'
                onClick={onNext}
                disabled={!hasNext}
                className='inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-gov-forest dark:text-emerald-100 transition-colors hover:bg-gov-forest/10 disabled:cursor-not-allowed disabled:opacity-30'>
                <span className='hidden sm:inline'>
                  {nextLabel ? `Art. ${nextLabel}` : 'Next'}
                </span>
                <span className='sm:hidden'>Next</span>
                <ArrowRight size={16} />
              </button>
            )}
          </footer>
        </motion.article>
      </AnimatePresence>
    </div>
  );
}
