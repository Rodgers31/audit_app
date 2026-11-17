'use client';

import type { RunSearchResult, SearchHit } from '@/data/constitution/search';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import { X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';

import { highlightSearch } from './prose';

type SearchState =
  | { query: string; result: RunSearchResult }
  | { query: string; error: true };

interface ReaderSearchProps {
  id: string;
  open: boolean;
  initialQuery: string;
  onClose: () => void;
  onSelect: (chapter: number, article: number, query: string, queryTerms?: string[]) => void;
}

function groupByChapter(hits: SearchHit[]) {
  const groups = new Map<number, SearchHit[]>();
  for (const hit of hits) {
    const chapter = hit.chapter.number;
    const group = groups.get(chapter);
    if (group) group.push(hit);
    else groups.set(chapter, [hit]);
  }
  return Array.from(groups);
}

export default function ReaderSearch({ id, open, initialQuery, onClose, onSelect }: ReaderSearchProps) {
  const { lang } = useLang();
  const [value, setValue] = useState(initialQuery);
  const [state, setState] = useState<SearchState | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const helpId = useId();
  const query = value.trim();

  useEffect(() => {
    if (open) input.current?.focus({ preventScroll: true });
  }, [open]);

  useEffect(() => {
    if (!open || !query) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const { runSearch } = await import('@/data/constitution/search');
        const result = await runSearch(query, 20, { includeSemantic: false });
        if (!cancelled) setState({ query, result });
      } catch {
        if (!cancelled) setState({ query, error: true });
      }
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  const current = state?.query === query ? state : null;
  const result = current && 'result' in current ? current.result : null;
  const hits = result?.hits ?? [];
  let status = '';
  if (query) {
    if (!current) status = learnCopy(lang, 'readerSearchLoading');
    else if ('error' in current) status = learnCopy(lang, 'readerSearchError');
    else if (current.result.mode === 'too-short') status = learnCopy(lang, 'readerSearchShort');
    else if (hits.length === 0) status = learnCopy(lang, 'readerSearchEmpty');
    else status = learnCopy(lang, hits.length === 1 ? 'readerSearchResult' : 'readerSearchResults', { count: hits.length });
  }

  return (
    <div
      id={id}
      hidden={!open}
      data-reader-search
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          onClose();
        }
      }}
      className='space-y-2 border-b border-neutral-border px-4 py-3 sm:px-6'>
      <search aria-label={learnCopy(lang, 'readerSearchLabel')} className='space-y-2'>
        <label htmlFor={inputId} className='block text-sm font-semibold text-neutral-text'>
          {learnCopy(lang, 'readerSearchLabel')}
        </label>
        <div className='relative sm:max-w-xl'>
          <input
            ref={input}
            id={inputId}
            type='search'
            value={value}
            autoComplete='off'
            onChange={(event) => {
              setValue(event.target.value);
              setState(null);
            }}
            aria-describedby={helpId}
            placeholder={learnCopy(lang, 'readerSearchPlaceholder')}
            className='min-h-11 w-full rounded border border-neutral-border bg-surface-base pl-3 pr-12 text-base text-neutral-text placeholder:text-neutral-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good [&::-webkit-search-cancel-button]:hidden'
          />
          {value && (
            <button
              type='button'
              aria-label={learnCopy(lang, 'readerSearchClear')}
              onClick={() => {
                setValue('');
                setState(null);
                input.current?.focus();
              }}
              className='absolute inset-y-0 right-0 grid min-h-11 min-w-11 place-items-center rounded text-neutral-text hover:bg-surface-sunken focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-signal-good'>
              <X aria-hidden='true' size={16} />
            </button>
          )}
        </div>
        <p id={helpId} className='text-sm text-neutral-muted'>{learnCopy(lang, 'readerSearchHelp')}</p>
        <p role='status' className='text-sm text-neutral-muted'>{status}</p>
        {hits.length > 0 && (
          <div className='max-h-[45vh] overflow-y-auto overscroll-contain rounded border border-neutral-border'>
            {groupByChapter(hits).map(([chapter, chapterHits]) => (
              <section key={chapter} aria-labelledby={`${id}-chapter-${chapter}`} className='border-b border-neutral-border last:border-b-0'>
                <h4 id={`${id}-chapter-${chapter}`} className='border-b border-neutral-border bg-surface-sunken px-3 py-2 text-sm font-semibold text-neutral-text'>
                  {learnCopy(lang, 'readerSearchChapter', { chapter })} · <span lang='en'>{chapterHits[0].chapter.title}</span>
                </h4>
                <ul className='divide-y divide-neutral-border'>
                  {chapterHits.map(({ article, excerpt, isArticleLookup }) => (
                    <li key={article.number}>
                      <a
                        href={`?article=${article.number}`}
                        onClick={(event) => {
                          if (event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
                          event.preventDefault();
                          onSelect(chapter, article.number, query, result?.highlightTerms);
                        }}
                        className='block min-h-11 px-3 py-2 text-neutral-text hover:bg-surface-elevated focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-signal-good'>
                        <span className='block text-sm font-semibold'>
                          <span className='font-mono text-signal-alarm'>{highlightSearch(learnCopy(lang, 'article', { number: article.number }), isArticleLookup ? String(article.number) : query)}</span>{' '}
                          <span lang='en'>{highlightSearch(article.title, query, result?.highlightTerms)}</span>
                        </span>
                        {!isArticleLookup && excerpt && (
                          <span lang='en' className='mt-0.5 block text-sm text-neutral-muted'>
                            {highlightSearch(excerpt, query, result?.highlightTerms)}
                          </span>
                        )}
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </search>
    </div>
  );
}
