/**
 * ConstitutionBook — interactive "book" reader for the Constitution of Kenya.
 *
 * Responsibilities
 *   - Owns the active chapter + article state.
 *   - Lazily fetches chapter bodies through loadChapter() (cached).
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
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import { Menu, Search, X } from 'lucide-react';
import { useCallback, useEffect, useId, useMemo, useRef, useState, type TouchEvent } from 'react';

import ArticleViewer, { type ReadingMode } from './ArticleViewer';
import ChapterSidebar from './ChapterSidebar';
import ReaderSearch from './ReaderSearch';
import type { ReferenceTarget } from './prose';
import { DEFAULT_READER_LOCATION, pushArticleLocation, readArticleLocation } from './readerLocation';

const READING_MODE_KEY = 'auditgava-constitution-reading-mode';

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
  initialChapter = DEFAULT_READER_LOCATION.chapter,
  initialArticle = DEFAULT_READER_LOCATION.article,
  seedQuery = '',
}: ConstitutionBookProps) {
  /* ── State ── */
  const [activeChapter, setActiveChapter] = useState<number>(initialChapter);
  const [activeArticle, setActiveArticle] = useState<number | null>(initialArticle ?? null);
  const [loadedChapter, setLoadedChapter] = useState<ConstitutionChapter | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const { lang } = useLang();
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [mode, setMode] = useState<ReadingMode>('plain');
  const drawerButton = useRef<HTMLButtonElement>(null);
  const searchPanelId = useId();
  const searchButton = useRef<HTMLButtonElement>(null);
  const articleTitle = useRef<HTMLHeadingElement>(null);
  const pendingSearchFocus = useRef(false);
  const [searchOpen, setSearchOpen] = useState(() => Boolean(seedQuery));
  const [searchSelection, setSearchSelection] = useState<{ article: number; query: string; terms?: string[] } | null>(null);
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
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

  useEffect(() => {
    const requested = readArticleLocation();
    if (requested) {
      setActiveChapter(requested.chapter);
      setActiveArticle(requested.article);
    }
    try {
      if (localStorage.getItem(READING_MODE_KEY) === 'official') setMode('official');
    } catch {
      // The current page still works if the browser restricts storage.
    }

    function restoreArticle() {
      pendingSearchFocus.current = false;
      const location = readArticleLocation() ?? DEFAULT_READER_LOCATION;
      setActiveChapter(location.chapter);
      setActiveArticle(location.article);
      setRefHistory([]);
      setHighlightClause(null);
    }
    window.addEventListener('popstate', restoreArticle);
    return () => window.removeEventListener('popstate', restoreArticle);
  }, []);

  function changeMode(value: ReadingMode) {
    setMode(value);
    setHighlightClause(null);
    try {
      localStorage.setItem(READING_MODE_KEY, value);
    } catch {
      // Keep the in-memory choice if persistence isn't available.
    }
  }

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
  const chapter = loadedChapter?.number === activeChapter ? loadedChapter : null;
  const articleList = chapter?.articles;
  const currentIdx = useMemo(() => {
    if (activeArticle === null) return -1;
    return articleList?.findIndex((a) => a.number === activeArticle) ?? -1;
  }, [articleList, activeArticle]);
  const currentArticle = currentIdx >= 0 ? articleList?.[currentIdx] : null;
  const articleSearch = searchSelection?.article === currentArticle?.number ? searchSelection : null;
  const prevArticle = currentIdx > 0 ? articleList?.[currentIdx - 1] : null;
  const nextArticle = currentIdx >= 0 ? articleList?.[currentIdx + 1] : null;

  /* ── Navigation helpers ── */
  const goPrev = useCallback(() => {
    if (prevArticle) {
      setActiveArticle(prevArticle.number);
      setHighlightClause(null);
      pushArticleLocation(prevArticle.number);
    }
  }, [prevArticle]);

  const goNext = useCallback(() => {
    if (nextArticle) {
      setActiveArticle(nextArticle.number);
      setHighlightClause(null);
      pushArticleLocation(nextArticle.number);
    }
  }, [nextArticle]);

  const selectChapter = useCallback(
    (n: number) => {
      if (n === activeChapter) return;
      const first = CONSTITUTION_META.find((item) => item.number === n)?.articleTitles[0];
      if (!first) return;
      setActiveChapter(n);
      setActiveArticle(first.number);
      pushArticleLocation(first.number);
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
    selectChapter(nextChapterMeta.number);
  }, [nextChapterMeta, selectChapter]);

  const selectArticle = useCallback(
    (chapterNumber: number, articleNumber: number) => {
      setActiveChapter(chapterNumber);
      setActiveArticle(articleNumber);
      setRefHistory([]);
      setHighlightClause(null);
      pushArticleLocation(articleNumber);
    },
    []
  );

  function selectSearchResult(chapterNumber: number, articleNumber: number, query: string, terms?: string[]) {
    pendingSearchFocus.current = true;
    setSearchSelection({ article: articleNumber, query, terms });
    setSearchOpen(false);
    selectArticle(chapterNumber, articleNumber);
  }

  useEffect(() => {
    if (!pendingSearchFocus.current || !searchSelection) return;
    if (activeArticle !== searchSelection.article) {
      pendingSearchFocus.current = false;
    } else if (currentArticle?.number === searchSelection.article) {
      pendingSearchFocus.current = false;
      articleTitle.current?.focus({ preventScroll: true });
      articleTitle.current?.scrollIntoView({ block: 'nearest' });
    }
  }, [activeArticle, currentArticle, searchSelection]);

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
      const next = target.kind === 'article'
        ? target.articleNumber
        : CONSTITUTION_META.find((item) => item.number === target.chapterNumber)?.articleTitles[0]?.number;
      if (next == null) return;
      setActiveChapter(target.chapterNumber);
      setActiveArticle(next);
      pushArticleLocation(next);
    },
    [activeChapter, activeArticle]
  );

  const goBack = useCallback(() => {
    const prev = refHistory[refHistory.length - 1];
    if (!prev) return;
    setRefHistory((history) => history.slice(0, -1));
    setActiveChapter(prev.chapter);
    setActiveArticle(prev.article);
    pushArticleLocation(prev.article);
    setHighlightClause(null);
  }, [refHistory]);

  /* ── Keyboard navigation (arrow keys) ── */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.metaKey || e.ctrlKey ||
        (e.target as HTMLElement | null)?.closest?.('input, textarea, select, [contenteditable="true"], [data-reader-search]')) return;
      if (e.key === 'ArrowRight') goNext();
      else if (e.key === 'ArrowLeft') goPrev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [goNext, goPrev]);

  /* ── Mobile swipe ── */
  function startSwipe({ touches, target }: TouchEvent) {
    const touch = touches.length === 1 ? touches[0] : undefined;
    swipeStart.current = touch && target instanceof Element && !target.closest('button, a, label, summary')
      ? { x: touch.clientX, y: touch.clientY }
      : null;
  }

  function endSwipe({ changedTouches }: TouchEvent) {
    const start = swipeStart.current;
    const touch = changedTouches[0];
    swipeStart.current = null;
    if (!start || !touch) return;
    const distance = touch.clientX - start.x;
    if (Math.abs(distance) < 80 || Math.abs(distance) <= 2 * Math.abs(touch.clientY - start.y)) return;
    if (distance < 0) goNext();
    else goPrev();
  }

  const activeMeta = CONSTITUTION_META.find((m) => m.number === activeChapter);
  const articlesLeft = (articleList?.length ?? 0) - currentIdx - 1;
  const remaining = learnCopy(lang, articlesLeft === 1 ? 'chapterProgressOne' : 'chapterProgress', {
    count: articlesLeft, chapter: activeChapter,
  });
  const closeDrawer = () => {
    setDrawerOpen(false);
    drawerButton.current?.focus();
  };

  return (
    <section
      id='constitution-book'
      className='relative scroll-mt-20 overflow-hidden rounded border border-neutral-border bg-surface-base'
      aria-label={learnCopy(lang, 'readerTitle')}>
      {/* ── Header ── */}
      <div className='flex flex-wrap items-center justify-between gap-3 border-b border-neutral-border px-4 py-3 sm:px-6'>
        <h3 className='font-display text-xl font-semibold text-neutral-text sm:text-2xl'>
          {learnCopy(lang, 'bookHeading')}
        </h3>
        <div className='flex flex-wrap gap-2'>
          <button
            ref={searchButton}
            type='button'
            className='audit-control bg-surface-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good'
            aria-expanded={searchOpen}
            aria-controls={searchPanelId}
            data-reader-search
            onClick={() => setSearchOpen((open) => !open)}>
            <Search aria-hidden='true' size={16} />
            {learnCopy(lang, 'readerSearch')}
          </button>
          <button
            type='button'
            ref={drawerButton}
            className='inline-flex min-h-11 items-center gap-2 rounded border border-neutral-border bg-surface-elevated px-3 text-sm font-semibold text-neutral-text hover:bg-surface-sunken lg:hidden'
            onClick={() => setDrawerOpen((v) => !v)}
            onKeyDown={({ key }) => { if (key === 'Escape' && drawerOpen) closeDrawer(); }}
            aria-expanded={drawerOpen}
            aria-controls='constitution-drawer'>
            {drawerOpen ? <X aria-hidden='true' size={16} /> : <Menu aria-hidden='true' size={16} />}
            {learnCopy(lang, 'chapters')}
          </button>
        </div>
      </div>
      <ReaderSearch
        id={searchPanelId}
        open={searchOpen}
        initialQuery={seedQuery}
        onClose={() => {
          setSearchOpen(false);
          searchButton.current?.focus();
        }}
        onSelect={selectSearchResult}
      />

      {/* ── Body ── */}
      <div className='grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)]'>
        {/* Sidebar — desktop */}
        <aside className='hidden max-h-[640px] overflow-y-auto border-r border-neutral-border bg-surface-elevated p-3 lg:block'>
          <ChapterSidebar
            chapters={CONSTITUTION_META}
            activeChapterNumber={activeChapter}
            activeArticleNumber={activeArticle}
            loadedChapter={chapter}
            onSelectChapter={selectChapter}
            onSelectArticle={selectArticle}
          />
        </aside>

        {/* Sidebar — mobile drawer */}
        <aside
          id='constitution-drawer'
          hidden={!drawerOpen}
          onKeyDown={(event) => { if (event.key === 'Escape') closeDrawer(); }}
          className='max-h-[60vh] overflow-y-auto border-b border-neutral-border bg-surface-elevated p-3 lg:hidden'>
          {drawerOpen && (
            <ChapterSidebar
              chapters={CONSTITUTION_META}
              activeChapterNumber={activeChapter}
              activeArticleNumber={activeArticle}
              loadedChapter={chapter}
              onSelectChapter={selectChapter}
              onSelectArticle={selectArticle}
              onNavigate={closeDrawer}
            />
          )}
        </aside>

        {/* Viewer */}
        <div
          className='min-w-0 touch-pan-y touch-pinch-zoom'
          onTouchStart={startSwipe}
          onTouchEnd={endSwipe}
          onTouchCancel={() => { swipeStart.current = null; }}>
          <div className='bg-surface-sunken px-4 py-2 text-xs font-semibold text-neutral-text sm:px-6'>
            <div className='flex flex-wrap justify-between gap-x-3 gap-y-1'>
              <span>{learnCopy(lang, 'chapterTitle', { chapter: activeChapter, title: activeMeta?.title ?? '' })}</span>
              {currentArticle && <span>{remaining}</span>}
            </div>
            {currentArticle && articleList && (
              <progress
                className='mt-2 block h-1.5 w-full appearance-none overflow-hidden rounded bg-neutral-border [&::-moz-progress-bar]:bg-gov-sage [&::-webkit-progress-bar]:bg-neutral-border [&::-webkit-progress-value]:bg-gov-sage'
                aria-label={remaining}
                value={currentIdx + 1}
                max={articleList.length}
              />
            )}
          </div>
          {currentArticle ? (
            <ArticleViewer
              article={currentArticle}
              titleRef={articleTitle}
              query={articleSearch?.query ?? seedQuery}
              queryTerms={articleSearch?.terms}
              mode={highlightClause ? 'official' : mode}
              onModeChange={changeMode}
              prevArticle={prevArticle?.number}
              nextArticle={nextArticle?.number}
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
          ) : (
            <p role='status' className='p-6 text-sm text-neutral-muted'>
              {isLoading || (loadedChapter && !chapter)
                ? learnCopy(lang, 'loading')
                : learnCopy(lang, 'loadError', { chapter: activeChapter })}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
