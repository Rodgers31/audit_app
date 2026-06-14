/**
 * ConstitutionBook — interactive "book" reader for the Constitution of Kenya.
 *
 * Responsibilities
 *   - Owns the active chapter + article state.
 *   - Lazily fetches chapter bodies through loadChapter() (cached).
 *   - Drives page-turn direction for ArticleViewer's AnimatePresence.
 *   - Wires up keyboard arrows and mobile swipe gestures.
 *
 * Design choices
 *   - Chapters ship via a pre-computed CONSTITUTION_META array so the
 *     sidebar paints instantly; article bodies stream in per chapter.
 *   - Desktop: sidebar + viewer side-by-side. Mobile: sidebar collapses
 *     behind a drawer toggle.
 */
'use client';

import { CONSTITUTION_META, loadChapter } from '@/data/constitution';
import type { ConstitutionChapter } from '@/data/constitution/types';
import { AnimatePresence, motion, type PanInfo } from 'framer-motion';
import { BookOpen, Menu, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import ArticleViewer from './ArticleViewer';
import ChapterSidebar from './ChapterSidebar';
import type { ReferenceTarget } from './prose';

interface ConstitutionBookProps {
  /** Initial chapter to open. Defaults to Chapter 12 (Public Finance). */
  initialChapter?: number;
  /** Initial article within that chapter. Defaults to first. */
  initialArticle?: number;
  /**
   * Query string from the hero search — used to highlight matching
   * text inside the currently open article.
   */
  seedQuery?: string;
}

export default function ConstitutionBook({
  initialChapter = 12,
  initialArticle,
  seedQuery = '',
}: ConstitutionBookProps) {
  /* ── State ── */
  const [activeChapter, setActiveChapter] = useState<number>(initialChapter);
  const [activeArticle, setActiveArticle] = useState<number | null>(initialArticle ?? null);
  const [loadedChapter, setLoadedChapter] = useState<ConstitutionChapter | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [direction, setDirection] = useState<number>(1);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  // Breadcrumb of positions the reader left when they clicked a
  // reference inside the prose. Pushed in navigateToReference(),
  // popped in goBack(), cleared when the reader jumps via the sidebar
  // (that's general navigation — the back-pill only makes sense when
  // the user is following a chain of cross-references).
  const [refHistory, setRefHistory] = useState<
    Array<{ chapter: number; article: number }>
  >([]);
  // Top-level clause to flash + scroll into view after a reference
  // click. Set in navigateToReference when the reference named a
  // subparagraph (e.g. "Article 144(3)(c)" → "3"); cleared on every
  // other navigation path. Plain "Article 144" refs don't set a
  // clause, so the viewer mounts with no flash — the page switch
  // itself is the feedback.
  const [highlightClause, setHighlightClause] = useState<string | null>(null);

  /* Use a ref for direction too so keyboard/swipe handlers always read the
     latest value regardless of render timing. */
  const directionRef = useRef(1);
  useEffect(() => {
    directionRef.current = direction;
  }, [direction]);

  /* ── Fetch chapter body whenever the active chapter changes ── */
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    loadChapter(activeChapter).then((data) => {
      if (cancelled) return;
      setLoadedChapter(data);
      setIsLoading(false);
      if (data && data.articles.length > 0) {
        setActiveArticle((prev) => {
          // If caller preselected an article that lives in this chapter, honour it.
          if (prev !== null && data.articles.some((a) => a.number === prev)) {
            return prev;
          }
          return data.articles[0]!.number;
        });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeChapter]);

  /* ── Derive current article + neighbours ── */
  const articleList = loadedChapter?.articles ?? [];
  const currentIdx = useMemo(() => {
    if (activeArticle === null) return -1;
    return articleList.findIndex((a) => a.number === activeArticle);
  }, [articleList, activeArticle]);
  const currentArticle = currentIdx >= 0 ? articleList[currentIdx] : null;
  const prevArticle = currentIdx > 0 ? articleList[currentIdx - 1] : null;
  const nextArticle =
    currentIdx >= 0 && currentIdx < articleList.length - 1 ? articleList[currentIdx + 1] : null;

  /* ── Navigation helpers ── */
  const goPrev = useCallback(() => {
    if (prevArticle) {
      setDirection(-1);
      setActiveArticle(prevArticle.number);
      setHighlightClause(null);
    }
  }, [prevArticle]);

  const goNext = useCallback(() => {
    if (nextArticle) {
      setDirection(1);
      setActiveArticle(nextArticle.number);
      setHighlightClause(null);
    }
  }, [nextArticle]);

  const selectChapter = useCallback(
    (n: number) => {
      if (n === activeChapter) return;
      setDirection(n > activeChapter ? 1 : -1);
      setActiveChapter(n);
      // Drop the preselected article so the new chapter opens at #1.
      setActiveArticle(null);
      // Sidebar / keyboard jumps aren't "following a reference", so the
      // back-pill would be misleading here — start fresh.
      setRefHistory([]);
      setHighlightClause(null);
    },
    [activeChapter]
  );

  /** Next chapter in reading order (or null when we're on the last one). */
  const nextChapterMeta = useMemo(() => {
    const idx = CONSTITUTION_META.findIndex((m) => m.number === activeChapter);
    if (idx < 0 || idx >= CONSTITUTION_META.length - 1) return null;
    return CONSTITUTION_META[idx + 1]!;
  }, [activeChapter]);

  const goNextChapter = useCallback(() => {
    if (!nextChapterMeta) return;
    setDirection(1);
    setActiveChapter(nextChapterMeta.number);
    setActiveArticle(null);
    setHighlightClause(null);
  }, [nextChapterMeta]);

  const selectArticle = useCallback(
    (chapterNumber: number, articleNumber: number) => {
      if (chapterNumber !== activeChapter) {
        setDirection(chapterNumber > activeChapter ? 1 : -1);
        setActiveChapter(chapterNumber);
        setActiveArticle(articleNumber);
      } else {
        setDirection(articleNumber > (activeArticle ?? 0) ? 1 : -1);
        setActiveArticle(articleNumber);
      }
      setHighlightClause(null);
    },
    [activeChapter, activeArticle]
  );

  /** Follow a cross-reference from inside the prose. Pushes the
   * current location onto refHistory so the viewer's Back pill can
   * rewind — possibly across several hops. Chapter refs land on the
   * chapter's first article. No-ops when the reference points at
   * wherever the reader already is (self-references appear in summary
   * text often enough to matter). */
  const navigateToReference = useCallback(
    (target: ReferenceTarget) => {
      const sameChapter = target.chapterNumber === activeChapter;
      const sameArticle =
        target.kind === 'article' && sameChapter && target.articleNumber === activeArticle;
      const sameChapterStart = target.kind === 'chapter' && sameChapter;
      if (sameArticle || sameChapterStart) return;

      if (activeArticle !== null) {
        setRefHistory((h) => [...h, { chapter: activeChapter, article: activeArticle }]);
      }
      // Only flash when the reference explicitly named a clause. A
      // bare "Article 144" lands on the article with no highlight —
      // the page switch is the feedback, the whole-article flash we
      // had before was over-reaching.
      setHighlightClause(
        target.kind === 'article' && target.clauses.length > 0 ? target.clauses[0]! : null,
      );
      if (target.kind === 'chapter') {
        setDirection(target.chapterNumber > activeChapter ? 1 : -1);
        setActiveChapter(target.chapterNumber);
        setActiveArticle(null); // fall through to first article
        return;
      }
      // Article ref — same logic as selectArticle but we already
      // managed direction / state above.
      if (!sameChapter) {
        setDirection(target.chapterNumber > activeChapter ? 1 : -1);
        setActiveChapter(target.chapterNumber);
        setActiveArticle(target.articleNumber);
      } else {
        setDirection(target.articleNumber > (activeArticle ?? 0) ? 1 : -1);
        setActiveArticle(target.articleNumber);
      }
    },
    [activeChapter, activeArticle]
  );

  const goBack = useCallback(() => {
    setRefHistory((h) => {
      if (h.length === 0) return h;
      const prev = h[h.length - 1]!;
      // Apply navigation as a side effect — React batches the history
      // slice + the chapter/article sets into one render.
      if (prev.chapter !== activeChapter) {
        setDirection(prev.chapter > activeChapter ? 1 : -1);
        setActiveChapter(prev.chapter);
        setActiveArticle(prev.article);
      } else {
        setDirection(prev.article > (activeArticle ?? 0) ? 1 : -1);
        setActiveArticle(prev.article);
      }
      return h.slice(0, -1);
    });
    // Returning somewhere the reader has already read shouldn't flash
    // — they know the content. Flashing would read as "new answer" and
    // be misleading.
    setHighlightClause(null);
  }, [activeChapter, activeArticle]);

  /* ── Keyboard navigation (arrow keys) ── */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === 'ArrowRight') goNext();
      else if (e.key === 'ArrowLeft') goPrev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [goNext, goPrev]);

  /* ── Mobile swipe ── */
  const handleDragEnd = useCallback(
    (_: unknown, info: PanInfo) => {
      const { offset, velocity } = info;
      const swipe = Math.abs(offset.x) * velocity.x;
      if (offset.x < -80 || swipe < -500) goNext();
      else if (offset.x > 80 || swipe > 500) goPrev();
    },
    [goNext, goPrev]
  );

  /* ── Progress meter ── */
  const progress = useMemo(() => {
    if (articleList.length === 0) return 0;
    return ((currentIdx + 1) / articleList.length) * 100;
  }, [currentIdx, articleList.length]);

  const activeMeta = CONSTITUTION_META.find((m) => m.number === activeChapter);

  return (
    <section
      id='constitution-book'
      className='relative overflow-hidden rounded-3xl border border-white/60 dark:border-neutral-border bg-gradient-to-br from-white/85 via-gov-cream/80 to-gov-sand dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated shadow-elevated'
      aria-label='Constitution of Kenya reader'>
      {/* ── Header ── */}
      <div className='flex items-start gap-3 border-b border-neutral-border/60 bg-gradient-to-r from-gov-forest via-gov-dark to-gov-forest px-5 py-4 sm:px-7'>
        <div className='flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gov-gold/90 text-gov-dark dark:text-white shadow-surface'>
          <BookOpen size={20} />
        </div>
        <div className='min-w-0 flex-1'>
          <div className='text-[11px] font-semibold uppercase tracking-widest text-gov-gold/90'>
            Constitution of Kenya · 2010
          </div>
          <h3 className='font-display text-xl leading-tight text-white sm:text-2xl'>
            Read the law that shapes every shilling
          </h3>
          <p className='mt-1 text-[11px] leading-snug text-white/60'>
            Unofficial reference for civic learning. The authoritative consolidated text is
            published by{' '}
            <a
              href='https://www.kenyalaw.org'
              target='_blank'
              rel='noopener noreferrer'
              className='underline hover:text-white/90'>
              Kenya Law
            </a>
            .
          </p>
        </div>
        <button
          type='button'
          className='ml-2 inline-flex h-10 items-center gap-1.5 rounded-lg bg-white/10 px-3 text-xs font-semibold text-white hover:bg-white/20 lg:hidden'
          onClick={() => setDrawerOpen((v) => !v)}
          aria-expanded={drawerOpen}
          aria-controls='constitution-drawer'>
          {drawerOpen ? <X size={16} /> : <Menu size={16} />}
          <span className='hidden sm:inline'>Chapters</span>
        </button>
      </div>

      {/* ── Body ── */}
      <div className='grid grid-cols-1 lg:grid-cols-[280px_1fr]'>
        {/* Sidebar — desktop */}
        <aside className='hidden max-h-[640px] overflow-y-auto border-r border-neutral-border/60 bg-white/50 dark:bg-surface-elevated p-3 lg:block'>
          <ChapterSidebar
            chapters={CONSTITUTION_META}
            activeChapterNumber={activeChapter}
            activeArticleNumber={activeArticle}
            loadedChapter={loadedChapter}
            onSelectChapter={selectChapter}
            onSelectArticle={selectArticle}
          />
        </aside>

        {/* Sidebar — mobile drawer */}
        <AnimatePresence>
          {drawerOpen && (
            <motion.aside
              id='constitution-drawer'
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25 }}
              className='overflow-hidden border-b border-neutral-border/60 bg-white/70 dark:bg-surface-elevated p-3 lg:hidden'>
              <ChapterSidebar
                chapters={CONSTITUTION_META}
                activeChapterNumber={activeChapter}
                activeArticleNumber={activeArticle}
                loadedChapter={loadedChapter}
                onSelectChapter={selectChapter}
                onSelectArticle={selectArticle}
                onNavigate={() => setDrawerOpen(false)}
              />
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Viewer */}
        <motion.div
          className='relative min-h-[540px] bg-white/70 dark:bg-surface-elevated'
          drag='x'
          dragConstraints={{ left: 0, right: 0 }}
          dragElastic={0.18}
          onDragEnd={handleDragEnd}>
          {isLoading && !loadedChapter ? (
            <div className='flex h-[540px] items-center justify-center text-sm text-neutral-muted'>
              <div className='animate-pulse'>Loading chapter…</div>
            </div>
          ) : !loadedChapter ? (
            <div className='flex h-[540px] items-center justify-center p-8 text-center text-sm text-neutral-muted'>
              Could not load Chapter {activeChapter}. Please try another chapter.
            </div>
          ) : currentArticle ? (
            <ArticleViewer
              chapter={loadedChapter}
              article={currentArticle}
              query={seedQuery}
              direction={direction}
              hasPrev={!!prevArticle}
              hasNext={!!nextArticle}
              prevLabel={prevArticle ? String(prevArticle.number) : undefined}
              nextLabel={nextArticle ? String(nextArticle.number) : undefined}
              onPrev={goPrev}
              onNext={goNext}
              nextChapterNumber={nextChapterMeta?.number}
              nextChapterTitle={nextChapterMeta?.title}
              onGoNextChapter={goNextChapter}
              onReferenceClick={navigateToReference}
              backTarget={
                refHistory.length > 0
                  ? { articleNumber: refHistory[refHistory.length - 1]!.article }
                  : null
              }
              onBack={goBack}
              highlightClause={highlightClause}
            />
          ) : null}
        </motion.div>
      </div>

      {/* ── Progress bar ── */}
      <div className='border-t border-neutral-border/60 bg-white/60 dark:bg-surface-elevated px-4 py-3 sm:px-6'>
        <div className='flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-neutral-muted'>
          <span>
            Chapter {activeChapter}{activeMeta ? ` — ${activeMeta.title}` : ''}
          </span>
          <span>
            {articleList.length > 0
              ? `${currentIdx + 1} of ${articleList.length}`
              : '—'}
          </span>
        </div>
        <div className='mt-2 h-1.5 overflow-hidden rounded-full bg-neutral-border/60'>
          <motion.div
            className='h-full rounded-full bg-gradient-to-r from-gov-sage to-gov-gold'
            initial={false}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>
        <div className='mt-2 hidden text-[11px] text-neutral-muted sm:block'>
          Tip · use ← and → keys to turn pages, or swipe on mobile.
        </div>
      </div>
    </section>
  );
}
