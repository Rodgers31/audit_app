/**
 * ChapterSidebar — chapter + article navigation for the Constitution book.
 *
 * Layout:
 *   - Chapters section lists all chapters we publish.
 *   - For the selected chapter, the article list expands inline.
 *   - A mobile drawer variant (handled by the parent) reuses the same tree.
 *
 * Why not a virtualised list? We ship 18 chapters and a few dozen articles
 * each. A plain scrollable <ul> is faster and simpler than a virtualised
 * grid here.
 */
'use client';

import type { ChapterMeta, ConstitutionChapter } from '@/data/constitution/types';
import { motion } from 'framer-motion';
import { BookOpen, ChevronDown, ChevronRight } from 'lucide-react';
import { memo } from 'react';

interface ChapterSidebarProps {
  chapters: ChapterMeta[];
  activeChapterNumber: number;
  activeArticleNumber: number | null;
  loadedChapter: ConstitutionChapter | null;
  onSelectChapter: (n: number) => void;
  onSelectArticle: (chapterNumber: number, articleNumber: number) => void;
  /** Close-drawer callback for the mobile variant. */
  onNavigate?: () => void;
}

function ChapterSidebarInner({
  chapters,
  activeChapterNumber,
  activeArticleNumber,
  loadedChapter,
  onSelectChapter,
  onSelectArticle,
  onNavigate,
}: ChapterSidebarProps) {
  return (
    <nav className='text-sm' aria-label='Constitution chapters'>
      <div className='flex items-center gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-gov-forest/70 dark:text-emerald-100/70'>
        <BookOpen size={13} />
        Chapters
      </div>
      <ul className='space-y-0.5'>
        {chapters.map((chapter) => {
          const isActive = chapter.number === activeChapterNumber;
          const articles = isActive && loadedChapter ? loadedChapter.articles : [];
          return (
            <li key={chapter.number}>
              <button
                type='button'
                onClick={() => {
                  onSelectChapter(chapter.number);
                  onNavigate?.();
                }}
                className={`group flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left transition-colors ${
                  isActive
                    ? 'bg-gov-forest text-white shadow-surface'
                    : 'text-gov-dark dark:text-white hover:bg-gov-forest/10'
                }`}>
                <span
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] font-bold ${
                    isActive ? 'bg-gov-gold text-gov-dark dark:text-white' : 'bg-gov-forest/10 text-gov-forest dark:text-emerald-100'
                  }`}>
                  {chapter.number}
                </span>
                <span className='min-w-0 flex-1'>
                  <span className={`block truncate font-semibold ${isActive ? '' : ''}`}>
                    {chapter.title}
                  </span>
                  <span
                    className={`block truncate text-[11px] ${
                      isActive ? 'text-white/70' : 'text-neutral-muted'
                    }`}>
                    Articles {chapter.articleRange[0]}–{chapter.articleRange[1]}
                  </span>
                </span>
                {isActive ? (
                  <ChevronDown size={14} className='mt-1 text-white/80' />
                ) : (
                  <ChevronRight size={14} className='mt-1 text-neutral-muted group-hover:text-gov-forest dark:text-emerald-100' />
                )}
              </button>

              {isActive && (
                <motion.ul
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.25 }}
                  className='ml-7 mt-1 space-y-0.5 overflow-hidden border-l border-gov-forest/20 pl-2'>
                  {(articles.length ? articles : chapter.articleTitles).map((a) => {
                    const isArticleActive = a.number === activeArticleNumber;
                    return (
                      <li key={a.number}>
                        <button
                          type='button'
                          onClick={() => {
                            onSelectArticle(chapter.number, a.number);
                            onNavigate?.();
                          }}
                          className={`flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-[13px] leading-snug transition-colors ${
                            isArticleActive
                              ? 'bg-gov-gold/20 font-semibold text-gov-forest dark:text-emerald-100'
                              : 'text-neutral-text hover:bg-gov-forest/5 hover:text-gov-forest dark:text-emerald-100'
                          }`}>
                          <span className='mt-[1px] w-8 shrink-0 text-[11px] font-semibold text-gov-forest/70 dark:text-emerald-100/70'>
                            {a.number}
                          </span>
                          <span className='min-w-0 flex-1 truncate'>{a.title}</span>
                        </button>
                      </li>
                    );
                  })}
                </motion.ul>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

const ChapterSidebar = memo(ChapterSidebarInner);
export default ChapterSidebar;
