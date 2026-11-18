'use client';

import {
  filterTerms, getCategoryCounts, GLOSSARY_CATEGORIES, glossaryTerms,
  type GlossaryCategoryId, type GlossaryExample, type GlossaryTerm,
} from '@/data/glossaryTerms';
import { type CivicFigure, type CivicFigureKey, getCivicFigures } from '@/lib/api/civic';
import { evidenceUrl } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import { learnCopy } from '@/lib/i18n/messages/learn';
import SmartBackLink from '@/lib/navigation/SmartBackLink';
import { formatKesWords } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowUpRight, ChevronDown, Search } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

type Theme = GlossaryCategoryId | 'all';
type CivicFigures = Partial<Record<CivicFigureKey, CivicFigure & { citation?: { url?: string } | null }>>;

const LETTERS = Array.from('ABCDEFGHIJKLMNOPQRSTUVWXYZ');
const sampleOrder = ['pending-bills', 'budget-execution', 'audit-qualified'];
const byId = new Map(glossaryTerms.map(term => [term.id, term]));
const counts = getCategoryCounts();
const availableCategories = GLOSSARY_CATEGORIES.filter(({ id }) => counts[id] > 0);
const categories = {
  all: 'glossaryAll',
  finance: 'glossaryFinance',
  planning: 'glossaryPlanning',
  spending: 'glossarySpending',
  accountability: 'glossaryAccountability',
  economy: 'glossaryEconomy',
  devolution: 'glossaryDevolution',
} as const;
const focusClass = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest dark:focus-visible:outline-emerald-100';
const linkClass = `inline-flex min-h-11 min-w-11 items-center gap-1 rounded text-sm font-semibold text-gov-forest underline underline-offset-4 dark:text-emerald-100 ${focusClass}`;

function firstLetter(term: GlossaryTerm) {
  return term.term[0].toUpperCase();
}

function orderedTerms(terms: GlossaryTerm[], featured: boolean) {
  const alphabetical = [...terms].sort((a, b) => a.term.localeCompare(b.term, 'en'));
  if (!featured) return alphabetical;
  return [
    ...sampleOrder.flatMap(id => alphabetical.filter(term => term.id === id)),
    ...alphabetical.filter(term => !sampleOrder.includes(term.id)),
  ];
}

function GlossaryExampleRow({ example, figures }: { example: GlossaryExample; figures?: CivicFigures }) {
  const { lang } = useLang();
  if (typeof example === 'string') return <li lang='en'>{example}</li>;
  const fig = figures?.[example.figure];
  const period = typeof fig?.period === 'string' ? fig.period.trim() : '';
  if (fig?.available !== true || !period || typeof fig.value !== 'number' || !Number.isFinite(fig.value) ||
      fig.value < 0 || typeof fig.unit !== 'string' || fig.unit.toLowerCase() !== 'kes' ||
      !['official', 'estimated', 'projected'].includes(fig.data_quality)) {
    return <li lang='en'>{example.fallback}</li>;
  }

  const value = formatKesWords(fig.value);
  const official = fig.data_quality === 'official';
  const text = official
    ? example.template.replace('{value}', value).replace('{period}', period)
    : learnCopy(lang, fig.data_quality === 'projected' ? 'glossaryForecast' : 'glossaryEstimate', { value, period });
  const sourceLink = evidenceUrl(fig.citation?.url);
  return (
    <li>
      <p lang={official ? 'en' : undefined}>{text}</p>
      {typeof fig.source === 'string' && fig.source.trim() && (
        <p className='mt-0.5 text-neutral-muted'>
          {learnCopy(lang, 'glossaryExampleSource')}{' '}<span lang='en'>{fig.source}</span>
        </p>
      )}
      {sourceLink && (
        <a href={sourceLink} className={linkClass}>{learnCopy(lang, 'glossaryOpenSource')} <ArrowUpRight size={16} aria-hidden='true' /></a>
      )}
    </li>
  );
}

function GlossaryCard({ term, open, onToggle, figures }: {
  term: GlossaryTerm; open: boolean; onToggle: () => void; figures?: CivicFigures;
}) {
  const { lang } = useLang();
  const detail = `term-detail-${term.id}`;
  return (
    <li id={`term-${term.id}`} className='scroll-mt-20 border-b border-neutral-border'>
      <h2>
        <button type='button' aria-expanded={open} aria-controls={detail} onClick={onToggle}
          className={`flex min-h-11 w-full items-center justify-between gap-3 rounded py-2 text-left font-semibold ${focusClass}`}>
          <span className='min-w-0 text-base' lang='en'>
            {term.term}{term.abbreviation && <span className='ml-2 text-sm text-neutral-muted'>{term.abbreviation}</span>}
          </span>
          <ChevronDown size={18} aria-hidden='true' className={open ? 'shrink-0 rotate-180' : 'shrink-0'} />
        </button>
      </h2>
      <p className='pb-2 text-sm leading-relaxed' lang='en'>{term.shortDef}</p>
      {(term.seenOn || term.articleContext) && (
        <div className='flex flex-wrap items-center gap-x-3 pb-1 text-sm'>
          {term.articleContext && term.relatedArticle && (
            <Link href={`/learn?article=${term.relatedArticle.article}`} className={linkClass}>
              <span className='sr-only'>{learnCopy(lang, 'glossaryContext')}{' '}</span>
              <span lang='en'>{term.relatedArticle.label}</span>
            </Link>
          )}
          {term.seenOn && (
            <div className='flex flex-wrap items-center gap-x-3'>
              <span className='font-semibold'>{learnCopy(lang, 'glossarySeen')}</span>
              {term.seenOn.map(({ href, label }) => <Link key={href} href={href} className={linkClass}>{learnCopy(lang, label)}</Link>)}
            </div>
          )}
        </div>
      )}
      <div id={detail} hidden={!open} className='space-y-3 pb-4 text-sm leading-relaxed'>
        {open && (
          <>
            <p lang='en'>{term.longDef}</p>
            <div>
              <h3 className='mb-1 font-semibold'>{learnCopy(lang, 'glossaryExamples')}</h3>
              <ul className='list-disc space-y-2 pl-5'>
                {term.examples.map((example, i) => <GlossaryExampleRow key={i} example={example} figures={figures} />)}
              </ul>
            </div>
            {term.definitionSource && (
              <div>
                <h3 className='font-semibold'>{learnCopy(lang, 'glossarySource')}</h3>
                <a href={term.definitionSource.href} className={linkClass} lang='en'>
                  <span className='min-w-0 break-words'>{term.definitionSource.label}</span>
                  <ArrowUpRight size={16} aria-hidden='true' className='shrink-0' />
                </a>
              </div>
            )}
            {term.relatedArticle && !term.articleContext && (
              <Link href={`/learn?article=${term.relatedArticle.article}`} className={linkClass} lang='en'>
                {term.relatedArticle.label}
              </Link>
            )}
            {term.relatedTerms && (
              <div>
                <h3 className='font-semibold'>{learnCopy(lang, 'glossaryRelated')}</h3>
                <ul className='flex flex-wrap gap-x-4'>
                  {term.relatedTerms.map(id => (
                    <li key={id}><a className={linkClass} href={`#term-${id}`} lang='en'>{byId.get(id)?.term}</a></li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </li>
  );
}

export default function InteractiveGlossary({ searchTerm = '' }: { searchTerm?: string }) {
  const { lang } = useLang();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<Theme>('all');
  const [letter, setLetter] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<{ id: string } | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const categoryInput = useRef<HTMLSelectElement>(null);
  const { data: civic } = useQuery({
    queryKey: ['civic-figures'],
    queryFn: ({ signal }) => getCivicFigures(signal),
    staleTime: 1000 * 60 * 60,
  });

  const reset = useCallback(() => {
    setSearch('');
    setCategory('all');
    setLetter(null);
  }, []);

  useEffect(() => {
    function revealHash() {
      const hash = window.location.hash;
      if (!hash.startsWith('#term-')) return;
      const id = hash.slice('#term-'.length);
      if (!byId.has(id)) return;
      reset();
      setOpenId(id);
      setAnchor({ id });
    }
    revealHash();
    window.addEventListener('hashchange', revealHash);
    return () => window.removeEventListener('hashchange', revealHash);
  }, [reset]);

  useLayoutEffect(() => {
    if (!anchor) return;
    const card = document.getElementById(`term-${anchor.id}`);
    card?.scrollIntoView({ block: 'start', behavior: 'instant' });
    card?.querySelector('button')?.focus({ preventScroll: true });
  }, [anchor]);

  const query = searchTerm || search;
  const filtered = filterTerms(glossaryTerms, query, category);
  const activeLetters = new Set(filtered.map(firstLetter));
  const activeLetter = letter && activeLetters.has(letter) ? letter : null;
  const filtering = Boolean(query.trim() || category !== 'all' || activeLetter);
  const shown = orderedTerms(activeLetter ? filtered.filter(term => firstLetter(term) === activeLetter) : filtered, !filtering);
  const resultText = !filtering
    ? learnCopy(lang, 'glossaryCoverage', { count: glossaryTerms.length, themes: availableCategories.length - 1 })
    : learnCopy(lang, shown.length === 1 ? 'glossaryOne' : 'glossaryCount', { count: shown.length });

  return (
    <div data-glossary-index className='space-y-3 text-neutral-text'>
      <div>
        <SmartBackLink href='/learn' className={`inline-flex min-h-11 items-center gap-2 rounded text-sm text-gov-forest underline-offset-4 hover:underline dark:text-emerald-100 ${focusClass}`}>
          <ArrowLeft size={16} aria-hidden='true' /> {learnCopy(lang, 'quizBack')}
        </SmartBackLink>
        <h1 className='font-display text-[clamp(1.625rem,4vw,2.25rem)] font-bold leading-tight'>{learnCopy(lang, 'glossaryTitle')}</h1>
      </div>
      {!searchTerm && (
        <label className='relative block'>
          <span className='sr-only'>{learnCopy(lang, 'glossarySearch')}</span>
          <Search size={18} aria-hidden='true' className='pointer-events-none absolute left-3 top-1/2 -translate-y-1/2' />
          <input ref={searchInput} type='search' value={search} onChange={event => { setSearch(event.target.value); setLetter(null); }}
            placeholder={learnCopy(lang, 'glossarySearchPlaceholder', { count: glossaryTerms.length })}
            className={`min-h-[46px] w-full rounded-md border border-neutral-text bg-surface-base pl-10 pr-3 text-base placeholder:text-neutral-muted ${focusClass}`} />
        </label>
      )}

      <div role='group' aria-label={learnCopy(lang, 'glossaryLetters')} className='flex max-w-full flex-wrap gap-2'>
        {LETTERS.map(key => (
          <button key={key} type='button' disabled={!activeLetters.has(key)} aria-pressed={activeLetter === key}
            onClick={() => setLetter(activeLetter === key ? null : key)}
            className={`grid size-11 place-items-center rounded border border-neutral-border bg-surface-base text-sm font-semibold enabled:hover:border-neutral-text aria-pressed:border-neutral-text aria-pressed:bg-neutral-text aria-pressed:text-surface-base disabled:border-transparent disabled:bg-transparent disabled:text-neutral-muted ${focusClass}`}>
            {key}
          </button>
        ))}
      </div>

      <div className='flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm'>
        <p role='status' className='text-neutral-text'>{resultText}</p>
        <div className='flex flex-wrap items-center gap-x-3'>
          <label className='flex min-w-0 flex-wrap items-center gap-2'>
            <span>{learnCopy(lang, 'glossaryCategory')}</span>
            <select ref={categoryInput} value={category} onChange={event => { setCategory(event.target.value as Theme); setLetter(null); }}
              className={`min-h-11 min-w-11 rounded border border-neutral-border bg-surface-base px-2 text-base ${focusClass}`}>
              {availableCategories.map(({ id }) => (
                <option key={id} value={id}>{learnCopy(lang, categories[id])} ({counts[id]})</option>
              ))}
            </select>
          </label>
          {filtering && (
            <button type='button' onClick={() => {
              reset();
              (searchInput.current ?? categoryInput.current)?.focus();
            }} className={linkClass}>{learnCopy(lang, 'glossaryReset')}</button>
          )}
        </div>
      </div>

      {shown.length ? (
        <ul className='border-t border-neutral-border'>
          {shown.map(term => <GlossaryCard key={term.id} term={term} open={openId === term.id}
            onToggle={() => setOpenId(openId === term.id ? null : term.id)} figures={civic?.figures} />)}
        </ul>
      ) : (
        <div className='rounded border border-neutral-border bg-surface-base p-4'>
          <h2 className='text-audit-heading font-semibold'>{learnCopy(lang, 'glossaryEmpty')}</h2>
          <p className='mt-1 text-sm'>{learnCopy(lang, 'glossaryEmptyHelp')}</p>
        </div>
      )}
    </div>
  );
}
