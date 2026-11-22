'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { PUBLIC_SEARCH_MESSAGES as copy } from '@/lib/i18n/messages/publicSearch';
import { useAuditFindings } from '@/lib/react-query/useAudits';
import { useNationalLoans } from '@/lib/react-query/useDebt';
import { AUDIT_SEARCH_LIMIT, findPublishedAuditResults, findPublishedLenderResults } from '@/lib/search/publishedSearch';
import { findLocalPublicResults, findPublicArticles, hasPublicSearchQuery, type ArticleSearch } from '@/lib/search/publicSearch';
import { Search, X } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useId, useRef, useState, type MouseEvent } from 'react';

type SearchState = ArticleSearch & { query: string };

interface ResultGroup {
  id: 'counties' | 'articles' | 'glossary' | 'findings' | 'lenders';
  results: Array<{ href: string; title: string; context?: string; key?: number }>;
  action?: string;
}

interface PublicSearchProps {
  autoFocus?: boolean;
  compact?: boolean;
  onNavigate?: () => void;
}

const focusClass = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good';
const SEARCHABLE_CHARACTER = new RegExp('[\\p{L}\\p{N}]', 'u');

export default function PublicSearch({ autoFocus = false, compact = false, onNavigate }: PublicSearchProps) {
  const { lang } = useLang();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState('');
  const [state, setState] = useState<SearchState | null>(null);
  const query = value.trim();
  const canSearch = hasPublicSearchQuery(query);
  const searchRecords = query.length >= 3 && SEARCHABLE_CHARACTER.test(query);
  // These endpoints return public collections, so every query filters the same
  // cached response locally. A late response can only match the current input.
  const audits = useAuditFindings({ page: 1, limit: AUDIT_SEARCH_LIMIT }, { enabled: searchRecords });
  const loans = useNationalLoans({ enabled: searchRecords });
  const auditData = searchRecords && !audits.isError && Array.isArray(audits.data?.items) ? audits.data : null;
  const loanData = searchRecords && !loans.isError && Array.isArray(loans.data?.loans) ? loans.data : null;

  useEffect(() => {
    if (autoFocus) input.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  useEffect(() => {
    if (!canSearch) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const result = await findPublicArticles(query);
        if (active) setState({ query, ...result });
      } catch {
        if (active) setState({ query, coverage: 'unavailable', articles: [] });
      }
    }, 180);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [canSearch, query]);

  const current = state?.query === query ? state : null;
  const local = findLocalPublicResults(query);
  const groups: ResultGroup[] = [
    { id: 'counties', results: local.counties },
    {
      id: 'findings',
      results: auditData ? findPublishedAuditResults(auditData, query) : [],
      action: copy.openReportPage[lang],
    },
    { id: 'articles', results: current?.articles.map(result => ({
      ...result,
      context: copy.article[lang].replace('{number}', String(result.number)),
    })) ?? [] },
    { id: 'glossary', results: local.glossary },
    {
      id: 'lenders',
      results: loanData ? findPublishedLenderResults(loanData, query) : [],
      action: copy.openLoanRegister[lang],
    },
  ];
  const visibleCount = groups.reduce((total, group) => total + group.results.length, 0);

  const resultCount = visibleCount === 0 ? '' : visibleCount === 1 ? copy.one[lang]
    : copy.many[lang].replace('{count}', String(visibleCount));
  let message = '';
  if (query && !canSearch) message = [resultCount, copy.short[lang]].filter(Boolean).join(' ');
  if (canSearch) {
    const loading = !current || (searchRecords && (audits.isPending || loans.isPending));
    const notices = [
      current && current.coverage !== 'complete' ? copy[current.coverage][lang] : '',
      searchRecords && !audits.isPending && !auditData ? copy.findingsUnavailable[lang] : '',
      searchRecords && !loans.isPending && !loanData ? copy.lendersUnavailable[lang] : '',
    ].filter(Boolean);
    const empty = !loading && notices.length === 0 && !resultCount;
    message = [empty ? copy.empty[lang] : resultCount, loading ? copy.loading[lang] : '', ...notices]
      .filter(Boolean).join(' ');
  }

  function handleNavigate(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
      onNavigate?.();
    }
  }

  function updateValue(next: string) {
    if (next.trim() !== query) setState(null);
    setValue(next);
  }

  return (
    <search aria-label={copy.label[lang]} className={`block min-w-0 space-y-2 ${compact ? '' : 'rounded bg-surface-base p-3'}`}>
      <label htmlFor={inputId} className={compact ? 'sr-only' : 'block text-base font-semibold text-neutral-text'}>{copy.label[lang]}</label>
      <p id={`${inputId}-help`} className={compact ? 'sr-only' : 'text-sm text-neutral-muted'}>{copy.help[lang]}</p>
      <div className='relative'>
        <Search aria-hidden='true' className='pointer-events-none absolute left-3 top-1/2 size-[18px] -translate-y-1/2 text-neutral-muted' />
        <input
          ref={input}
          id={inputId}
          type='search'
          value={value}
          autoComplete='off'
          spellCheck={false}
          placeholder={compact ? copy.placeholder[lang] : undefined}
          onChange={(event) => updateValue(event.target.value)}
          aria-describedby={`${inputId}-help`}
          className={`min-h-12 w-full rounded border border-neutral-text bg-surface-elevated pl-10 pr-12 text-base text-neutral-text placeholder:text-neutral-muted [&::-webkit-search-cancel-button]:hidden ${focusClass}`}
        />
        {value && (
          <button
            type='button'
            aria-label={copy.clear[lang]}
            onClick={() => {
              updateValue('');
              input.current?.focus();
            }}
            className={`absolute inset-y-0 right-px grid min-w-11 place-items-center rounded text-neutral-text hover:bg-surface-sunken focus-visible:-outline-offset-2 ${focusClass}`}>
            <X aria-hidden='true' size={18} />
          </button>
        )}
      </div>
      <p role='status' className={message ? 'text-sm text-neutral-muted' : 'sr-only'}>{message}</p>
      {auditData && (
        <p className='text-sm text-neutral-muted'>{copy.findingsCoverage[lang].replace('{limit}', String(AUDIT_SEARCH_LIMIT))}</p>
      )}
      {visibleCount > 0 && (
        <div className='overflow-hidden rounded border border-neutral-border bg-surface-base'>
          {groups.map(({ id, results, action }) => results.length > 0 && (
            <section key={id} aria-labelledby={`${inputId}-${id}`} className='border-b border-neutral-border last:border-b-0'>
              <h2 id={`${inputId}-${id}`} className='border-b border-neutral-border bg-surface-sunken px-3 py-2 font-display text-lg font-semibold text-neutral-text'>
                {copy[id][lang]}
              </h2>
              <ul className='divide-y divide-neutral-border' role='list'>
                {results.map(result => (
                  <li key={result.key ?? result.href}>
                    <Link
                      href={result.href}
                      prefetch={false}
                      onClick={handleNavigate}
                      className={`flex min-h-11 flex-wrap items-center gap-x-2 px-3 py-2 text-sm text-neutral-text [overflow-wrap:anywhere] hover:bg-surface-elevated hover:underline focus-visible:-outline-offset-2 ${focusClass}`}>
                      {id === 'articles' && <span className='font-mono text-neutral-muted'>{result.context}</span>}
                      <span lang={id === 'counties' ? undefined : 'en'} className='min-w-0 font-semibold'>{result.title}</span>
                      {id === 'findings' && result.context && (
                        <span lang='en' className='w-full text-neutral-muted'>{result.context}</span>
                      )}
                      {action && <span className='w-full text-neutral-muted'>{action}</span>}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </search>
  );
}
