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
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import { ChevronDown, ChevronRight } from 'lucide-react';
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
  const { lang } = useLang();
  return (
    <nav className='text-sm' aria-label={learnCopy(lang, 'chapters')}>
      <div className='px-3 py-2 text-sm font-semibold text-neutral-muted'>
        {learnCopy(lang, 'chapters')}
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
                aria-expanded={isActive}
                className={`group flex min-h-11 w-full items-start gap-2 rounded px-3 py-2 text-left transition-colors ${
                  isActive
                    ? 'bg-gov-forest text-white shadow-surface'
                    : 'text-gov-dark dark:text-white hover:bg-gov-forest/10'
                }`}>
                <span
                  className='mt-0.5 shrink-0 text-xs font-semibold'>
                  {chapter.number}
                </span>
                <span className='min-w-0 flex-1'>
                  <span lang='en' className='block break-words font-semibold'>
                    {chapter.title}
                  </span>
                  <span
                    className={`block text-xs ${
                      isActive ? 'text-white' : 'text-neutral-muted'
                    }`}>
                    {learnCopy(lang, 'articleRange', { first: chapter.articleRange[0], last: chapter.articleRange[1] })}
                  </span>
                </span>
                {isActive ? (
                  <ChevronDown size={14} className='mt-1 text-white/80' />
                ) : (
                  <ChevronRight size={14} className='mt-1 text-neutral-muted group-hover:text-gov-forest dark:text-emerald-100' />
                )}
              </button>

              {isActive && (
                <ul className='ml-7 mt-1 space-y-0.5 border-l border-neutral-border pl-2'>
                  {(articles.length ? articles : chapter.articleTitles).map((a) => {
                    const isArticleActive = a.number === activeArticleNumber;
                    return (
                      <li key={a.number}>
                        <button
                          type='button'
                          aria-current={isArticleActive ? 'true' : undefined}
                          onClick={() => {
                            onSelectArticle(chapter.number, a.number);
                            onNavigate?.();
                          }}
                          className={`flex min-h-11 w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[13px] leading-snug transition-colors ${
                            isArticleActive
                              ? 'bg-gov-gold/20 font-semibold text-gov-forest dark:text-emerald-100'
                              : 'text-neutral-text hover:bg-gov-forest/5 hover:text-gov-forest dark:text-emerald-100'
                          }`}>
                          <span className='shrink-0 text-xs font-semibold text-neutral-muted'>
                            {a.number}
                          </span>
                          <span lang='en' className='min-w-0 flex-1 break-words'>{a.title}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
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
