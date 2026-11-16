'use client';

import type { ConstitutionArticle } from '@/data/constitution/types';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import { ArrowLeft, ArrowRight, ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useId, useRef } from 'react';

import { renderProse, type ReferenceTarget } from './prose';

export type ReadingMode = 'plain' | 'official';

interface ArticleViewerProps {
  article: ConstitutionArticle;
  query?: string;
  mode: ReadingMode;
  onModeChange: (mode: ReadingMode) => void;
  prevArticle?: number;
  nextArticle?: number;
  onPrev: () => void;
  onNext: () => void;
  nextChapterNumber?: number;
  nextChapterTitle?: string;
  onGoNextChapter: () => void;
  onReferenceClick: (target: ReferenceTarget) => void;
  backTarget: { articleNumber: number } | null;
  onBack: () => void;
  highlightClause: string | null;
}

const ARTICLE_LINKS = {
  budget: { label: 'budget', href: '/budget' },
  countyMoney: { label: 'countyMoney', href: '/transparency' },
  debt: { label: 'debt', href: '/debt' },
  audits: { label: 'audits', href: '/audits' },
  countyAudits: { label: 'countyAudits', href: '/counties' },
} as const;

const LINKS_BY_ARTICLE: Record<number, readonly (keyof typeof ARTICLE_LINKS)[]> = {
  201: ['budget'],
  203: ['countyMoney'],
  214: ['debt'],
  217: ['countyMoney'],
  218: ['countyMoney'],
  219: ['countyMoney'],
  229: ['audits', 'countyAudits'],
};

const CONSTITUTION_SOURCE = 'https://new.kenyalaw.org/akn/ke/act/2010/constitution/eng%402010-09-03/source.pdf';

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
  article,
  query = '',
  mode,
  onModeChange,
  prevArticle,
  nextArticle,
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
  const { lang } = useLang();
  const modeId = useId();
  const clauseRef = useRef<HTMLParagraphElement>(null);
  const currentMode = article.summary ? mode : 'official';
  const proseOptions = { query, onRefClick: onReferenceClick };
  const links = LINKS_BY_ARTICLE[article.number];

  useEffect(() => {
    if (highlightClause) clauseRef.current?.scrollIntoView({ block: 'nearest' });
  }, [article.number, highlightClause]);

  return (
    <article className='space-y-3 px-4 py-4 sm:px-6'>
      {backTarget && (
        <button
          type='button'
          onClick={onBack}
          className='inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-gov-sage hover:underline'>
          <ArrowLeft aria-hidden='true' size={16} />
          {learnCopy(lang, 'backTo', { number: backTarget.articleNumber })}
        </button>
      )}
      <header className='flex items-baseline gap-2'>
        <span className='shrink-0 font-mono text-[13px] font-semibold text-signal-alarm'>
          {learnCopy(lang, 'article', { number: article.number })}
        </span>
        <h4 lang='en' className='min-w-0 break-words font-display text-[22px] font-semibold leading-tight text-neutral-text sm:text-2xl'>
          {highlight(article.title, query)}
        </h4>
      </header>

      <fieldset className='grid min-w-0 grid-cols-2 overflow-hidden rounded border border-neutral-border'>
        <legend className='sr-only'>{learnCopy(lang, 'textVersion')}</legend>
        {(['plain', 'official'] as const).map((option) => (
          <label key={option} className='min-w-0 first-of-type:border-r first-of-type:border-neutral-border'>
            <input
              type='radio'
              name={modeId}
              className='peer sr-only'
              checked={currentMode === option}
              disabled={option === 'plain' && !article.summary}
              onChange={() => onModeChange(option)}
            />
            <span className='grid min-h-11 cursor-pointer place-items-center px-2 py-1 text-center text-[13px] font-semibold text-neutral-text peer-checked:bg-gov-sage peer-checked:text-white peer-focus-visible:ring-2 peer-focus-visible:ring-inset peer-focus-visible:ring-gov-gold peer-disabled:cursor-default peer-disabled:text-neutral-muted'>
              {learnCopy(lang, option === 'plain' ? 'plainEnglish' : 'officialText')}
            </span>
          </label>
        ))}
      </fieldset>

      {currentMode === 'plain' && article.summary ? (
        <p lang='en' className='text-[15px] leading-relaxed text-neutral-text'>{renderProse(article.summary, proseOptions)}</p>
      ) : (
        <div className='space-y-3 text-[15px] leading-relaxed text-neutral-text'>
          {!article.summary && <p className='text-sm text-neutral-text'>{learnCopy(lang, 'plainUnavailable')}</p>}
          <p className='text-xs text-neutral-muted'>
            {learnCopy(lang, 'transcript')}{' '}
            <a
              href={CONSTITUTION_SOURCE}
              target='_blank'
              rel='noopener noreferrer'
              className='flex min-h-11 items-center font-semibold text-gov-sage underline underline-offset-2'>
              {learnCopy(lang, 'source')}
            </a>
          </p>
          {article.paragraphs.map((paragraph, index) => {
            const leading = /^\s*\((\w+)\)/.exec(paragraph)?.[1];
            const isTarget = !!highlightClause && leading === highlightClause;
            return (
              <p
                key={index}
                lang='en'
                ref={isTarget ? clauseRef : undefined}
                className={isTarget ? 'rounded border-l-4 border-gov-gold bg-surface-sunken px-3 py-2' : undefined}>
                {renderProse(paragraph, proseOptions)}
              </p>
            );
          })}
        </div>
      )}

      {links && (
        <div className='space-y-1.5'>
          <h5 className='text-sm font-semibold text-neutral-text'>{learnCopy(lang, 'where')}</h5>
          <ul className='space-y-1.5'>
            {links.map((key) => {
              const { href, label } = ARTICLE_LINKS[key];
              return (
                <li key={key}>
                  <Link href={href} className='flex min-h-11 items-center gap-1 rounded border border-neutral-border bg-surface-elevated px-3 text-[13px] font-semibold text-gov-sage hover:underline'>
                    {learnCopy(lang, label)}
                    <ChevronRight aria-hidden='true' size={16} />
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {article.explanation && (
        <details>
          <summary className='min-h-11 cursor-pointer py-3 text-sm font-semibold text-gov-sage'>
            {learnCopy(lang, 'why')}
          </summary>
          <p lang='en' className='text-[15px] leading-relaxed text-neutral-text'>
            {renderProse(article.explanation, proseOptions)}
          </p>
        </details>
      )}

      <footer className='flex items-center justify-between gap-3 border-t border-neutral-border pt-1 text-sm font-semibold text-gov-sage'>
        {prevArticle != null && (
          <button type='button' onClick={onPrev} className='inline-flex min-h-11 items-center gap-2 hover:underline'>
            <ArrowLeft aria-hidden='true' size={16} />
            {learnCopy(lang, 'article', { number: prevArticle })}
          </button>
        )}
        {nextArticle != null ? (
          <button type='button' onClick={onNext} className='ml-auto inline-flex min-h-11 items-center gap-2 hover:underline'>
            {learnCopy(lang, 'article', { number: nextArticle })}
            <ArrowRight aria-hidden='true' size={16} />
          </button>
        ) : nextChapterNumber != null && (
          <button type='button' onClick={onGoNextChapter} className='ml-auto inline-flex min-h-11 items-center gap-2 text-left hover:underline'>
            {learnCopy(lang, 'chapterTitle', { chapter: nextChapterNumber, title: nextChapterTitle ?? '' })}
            <ArrowRight aria-hidden='true' size={16} />
          </button>
        )}
      </footer>
    </article>
  );
}
