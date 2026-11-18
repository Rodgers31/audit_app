'use client';

import { normalizeCountyName } from '@/lib/counties/regions';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_COMPARE_MESSAGES } from '@/lib/i18n/messages/countyCompare';
import { ChevronDown, Plus, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent, Ref } from 'react';
import { MAX_COMPARE_COUNTIES } from './ledgerData';

interface CountyOption {
  id: string;
  name: string;
}

const SUGGESTED_PAIRS = [['nairobi', 'kiambu'], ['turkana', 'marsabit']] as const;
const ACTION_CLASS = 'inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-lg px-2 text-sm font-semibold text-gov-forest hover:bg-gov-forest/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest dark:text-emerald-100 dark:hover:bg-emerald-100/10 dark:focus-visible:outline-emerald-100';

function getSuggestedCounty(all: CountyOption[], name: string) {
  const matches = all.filter((county) => {
    const normalized = normalizeCountyName(county.name);
    return normalized === name || (name === 'nairobi' && normalized === 'nairobicity');
  });
  return matches.length === 1 ? matches[0] : undefined;
}

function CountyField({
  choices,
  value,
  label,
  onSelect,
  inputRef,
  disabled,
}: {
  choices: CountyOption[];
  value: CountyOption | undefined;
  label: string;
  onSelect?: (id: string) => void;
  inputRef: Ref<HTMLInputElement>;
  disabled?: boolean;
}) {
  const { lang } = useLang();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const listRef = useRef<HTMLUListElement>(null);
  const term = normalizeCountyName(query ?? '');
  const matches = choices.filter((county) => normalizeCountyName(county.name).includes(term));
  const options = value && !term ? [
    ...matches,
    { id: '', name: COUNTY_COMPARE_MESSAGES.clear[lang] },
  ] : matches;
  const listOpen = open && options.length > 0;
  const optionId = (index: number) => `${id}-option-${index}`;

  useEffect(() => {
    if (active >= 0) listRef.current?.children[active]?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  function close() {
    setOpen(false);
    setQuery(null);
    setActive(-1);
  }

  function select(county: CountyOption) {
    onSelect?.(county.id);
    close();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowUp':
        event.preventDefault();
        setOpen(true);
        if (options.length) {
          const step = event.key === 'ArrowDown' ? 1 : -1;
          const start = step === 1 ? 0 : options.length - 1;
          setActive(active < 0 ? start : (active + step + options.length) % options.length);
        }
        break;
      case 'Enter':
        if (!open) {
          setOpen(true);
        } else {
          const county = active < 0 && term ? options[0] : options[active];
          if (county) select(county);
        }
        break;
      case 'Escape':
        if (open) {
          event.preventDefault();
          close();
        }
        break;
    }
  }

  return (
    <div className='relative min-w-0'>
      <label htmlFor={id} className='sr-only'>{label}</label>
      <input
        id={id}
        ref={inputRef}
        type='text'
        role='combobox'
        autoComplete='off'
        aria-autocomplete='list'
        aria-expanded={listOpen}
        aria-controls={listOpen ? `${id}-list` : undefined}
        aria-activedescendant={listOpen && options[active] ? optionId(active) : undefined}
        placeholder={COUNTY_COMPARE_MESSAGES.placeholder[lang]}
        value={query ?? value?.name ?? ''}
        disabled={disabled}
        onFocus={(event) => {
          event.currentTarget.select();
          setOpen(true);
        }}
        onClick={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(-1);
          setOpen(true);
        }}
        onBlur={close}
        onKeyDown={onKeyDown}
        className='min-h-11 w-full rounded-lg border border-gov-forest/70 bg-surface-base py-2 pl-2.5 pr-7 text-base font-semibold text-neutral-text placeholder:text-neutral-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest dark:border-neutral-muted/70 dark:focus-visible:outline-emerald-100'
      />
      <ChevronDown
        size={16}
        aria-hidden='true'
        className='pointer-events-none absolute right-2 top-3.5 text-neutral-muted'
      />
      {listOpen && (
        <ul
          id={`${id}-list`}
          ref={listRef}
          role='listbox'
          aria-label={label}
          className='absolute top-full z-20 mt-1 max-h-56 w-full min-w-0 overflow-y-auto rounded-lg border border-gray-300 bg-surface-base p-1 shadow-lg dark:border-neutral-border'>
          {options.map((county, index) => (
            <li
              key={county.id}
              id={optionId(index)}
              role='option'
              aria-selected={index === active}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => select(county)}
              className='flex min-h-11 cursor-pointer items-center break-words rounded-md px-2 py-1.5 text-sm font-medium text-neutral-text [overflow-wrap:anywhere] hover:bg-gov-forest/10 aria-selected:bg-gov-forest/10 dark:hover:bg-emerald-100/10 dark:aria-selected:bg-emerald-100/10'>
              {county.name}
            </li>
          ))}
        </ul>
      )}
      {open && !listOpen && (
        <p role='status' className='absolute top-full z-20 mt-1 w-full rounded-lg border border-gray-300 bg-surface-base p-2 text-sm text-neutral-text shadow-lg dark:border-neutral-border'>
          {COUNTY_COMPARE_MESSAGES.noMatches[lang]}
        </p>
      )}
    </div>
  );
}

export default function ComparePicker({
  all,
  selected,
  onChange,
  onPair,
  onAdd,
  onRemove,
  disabled,
}: {
  all: CountyOption[];
  selected: string[];
  onChange?: (index: number, countyId: string) => void;
  onPair?: (ids: string[]) => void;
  onAdd?: () => void;
  onRemove?: (index: number) => void;
  disabled?: boolean;
}) {
  const { lang, t } = useLang();
  const fields = useRef<Array<HTMLInputElement | null>>([]);
  const nextFocus = useRef<number | null>(null);
  const pairs = SUGGESTED_PAIRS.flatMap(([first, second]) => {
    const a = getSuggestedCounty(all, first);
    const b = getSuggestedCounty(all, second);
    return a && b && a.id !== b.id ? [[a, b] as const] : [];
  });

  useEffect(() => {
    if (nextFocus.current !== null) {
      fields.current[nextFocus.current]?.focus();
      nextFocus.current = null;
    }
  }, [selected.length]);

  return (
    <div
      data-compare-pickers
      aria-hidden={disabled || undefined}
      className='space-y-3 rounded-xl border border-gray-200 bg-surface-base p-3 sm:p-4 dark:border-neutral-border'>
      <div className={`grid grid-cols-2 gap-2 sm:gap-3 ${selected.length === 3 ? 'md:grid-cols-3' : ''} ${selected.length === 4 ? 'lg:grid-cols-4' : ''}`}>
        {selected.map((id, index) => {
          const label = `${t('compare.county_label')} ${index + 1}`;
          const choices = all.filter((county) => !selected.some((otherId, otherIndex) => county.id === otherId && otherIndex !== index));
          return (
            <div key={index} className='min-w-0'>
              <CountyField
                choices={choices}
                label={label}
                value={all.find((county) => county.id === id)}
                onSelect={(countyId) => onChange?.(index, countyId)}
                inputRef={(node) => { fields.current[index] = node; }}
                disabled={disabled}
              />
              {selected.length > 2 && (
                <button
                  type='button'
                  disabled={disabled}
                  aria-label={t('compare.remove_county').replace('{n}', String(index + 1))}
                  onClick={() => {
                    nextFocus.current = Math.min(index, selected.length - 2);
                    onRemove?.(index);
                  }}
                  className={ACTION_CLASS}>
                  <X aria-hidden='true' size={16} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      {selected.length < MAX_COMPARE_COUNTIES && (
        <button
          type='button'
          disabled={disabled}
          onClick={() => {
            nextFocus.current = selected.length;
            onAdd?.();
          }}
          className={`${ACTION_CLASS} ${selected.length === 3 ? 'hidden lg:inline-flex' : ''}`}>
          <Plus aria-hidden='true' size={16} />
          {COUNTY_COMPARE_MESSAGES.add[lang]}
        </button>
      )}
      {pairs.length > 0 && (
        <div role='group' aria-label={COUNTY_COMPARE_MESSAGES.suggestions[lang]} className='flex flex-wrap gap-2'>
          {pairs.map(([a, b]) => (
            <button
              key={a.id}
              type='button'
              disabled={disabled}
              onClick={() => onPair?.([a.id, b.id])}
              className={`${ACTION_CLASS} border border-gray-300 dark:border-neutral-border`}>
              {COUNTY_COMPARE_MESSAGES.pair[lang].replace('{first}', a.name).replace('{second}', b.name)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
