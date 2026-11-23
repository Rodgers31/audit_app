'use client';

import { findCountyLinks } from '@/lib/counties/lookup';
import { useLang } from '@/lib/i18n/LangProvider';
import { HOME_TOPICS_MESSAGES } from '@/lib/i18n/messages/homeTopics';
import { Search, X } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react';

export default function HomeCountySearch() {
  const { lang, ready } = useLang();
  const router = useRouter();
  const inputId = useId();
  const listId = `${inputId}-suggestions`;
  const inputRef = useRef<HTMLInputElement>(null);
  const optionRef = useRef<HTMLAnchorElement>(null);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const label = HOME_TOPICS_MESSAGES['home.county_search.label'][lang];
  const matches = findCountyLinks(query);
  const expanded = open && matches.length > 0;
  const active = expanded ? matches[activeIndex] : undefined;
  const activeId = active ? `${listId}-${active.key}` : undefined;
  const noMatches = open && query.trim() !== '' && matches.length === 0;

  useEffect(() => {
    optionRef.current?.scrollIntoView({ block: 'nearest' });
  }, [activeId]);

  function close() {
    setOpen(false);
    setActiveIndex(-1);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      close();
    } else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && matches.length) {
      event.preventDefault();
      const last = matches.length - 1;
      setOpen(true);
      setActiveIndex((index) => {
        if (event.key === 'ArrowDown') return index < last ? index + 1 : 0;
        return index > 0 ? index - 1 : last;
      });
    } else if (event.key === 'Enter' && expanded) {
      const selection = active ?? (matches.length === 1 ? matches[0] : undefined);
      if (!selection) return;
      event.preventDefault();
      close();
      router.push(selection.href);
    }
  }

  return (
    <div className='mt-3 max-w-sm'>
      <label htmlFor={inputId} className='sr-only'>{label}</label>
      <div className='relative'>
        <Search aria-hidden='true' className='pointer-events-none absolute left-3 top-1/2 size-[18px] -translate-y-1/2 text-neutral-muted' />
        <input
          id={inputId}
          ref={inputRef}
          type='text'
          role='combobox'
          aria-expanded={expanded}
          aria-controls={expanded ? listId : undefined}
          aria-activedescendant={activeId}
          aria-autocomplete='list'
          autoComplete='off'
          disabled={!ready}
          enterKeyHint='go'
          spellCheck={false}
          placeholder={HOME_TOPICS_MESSAGES['home.county_search.placeholder'][lang]}
          value={query}
          onBlur={close}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(-1);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
          className={`min-h-[46px] w-full rounded-md border border-neutral-text bg-surface-elevated pl-10 text-audit-control text-neutral-text placeholder:text-neutral-muted motion-reduce:transition-none [@media(pointer:coarse)]:text-base ${query ? 'pr-11' : 'pr-3'}`}
        />
        {query !== '' && (
          <button
            type='button'
            aria-label={HOME_TOPICS_MESSAGES['home.county_search.clear'][lang]}
            onClick={() => {
              setQuery('');
              inputRef.current?.focus();
              close();
            }}
            className='absolute right-px top-px grid size-11 place-items-center rounded-md text-neutral-text hover:bg-surface-sunken motion-reduce:transition-none'>
            <X aria-hidden='true' className='size-[18px]' />
          </button>
        )}
      </div>
      {expanded && (
        <ul id={listId} role='listbox' aria-label={label} className='mt-1 max-h-56 divide-y divide-neutral-border overflow-y-auto rounded-md border border-neutral-border bg-surface-base'>
          {matches.map((county, index) => (
            <li key={county.href} role='presentation'>
              <Link
                id={`${listId}-${county.key}`}
                ref={index === activeIndex ? optionRef : undefined}
                href={county.href}
                prefetch={false}
                tabIndex={-1}
                role='option'
                aria-selected={index === activeIndex}
                onMouseDown={(event) => event.preventDefault()}
                className='flex min-h-11 items-center px-3 py-2 text-audit-control hover:bg-surface-sunken hover:underline focus-visible:underline aria-selected:bg-surface-sunken aria-selected:underline motion-reduce:transition-none'>
                {county.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p role='status' className={noMatches ? 'mt-2 text-audit-control text-neutral-muted' : 'sr-only'}>
        {noMatches && HOME_TOPICS_MESSAGES['home.county_search.no_matches'][lang]}
      </p>
    </div>
  );
}
