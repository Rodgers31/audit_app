'use client';

import {
  AUDITS_MESSAGES,
  auditSectionLabel,
} from '@/lib/i18n/messages/audits';
import { useLang } from '@/lib/i18n/LangProvider';
import type { Lang } from '@/lib/i18n/messages';
import { useRecurringFindings } from '@/lib/react-query';
import { useEffect, useRef, useState } from 'react';

const PAGE_SIZE = 20;

interface RecurringEntry {
  index: number;
  entity: string;
  section: string;
  years: number[];
}

type AuditMessage = keyof typeof AUDITS_MESSAGES;

function markerClass(recorded: boolean) {
  return `size-2.5 shrink-0 rounded-full border border-neutral-muted ${recorded ? 'bg-neutral-text' : 'bg-transparent'}`;
}

function RecurringGroups({ entries, yearLabels, lang }: {
  entries: RecurringEntry[];
  yearLabels: number[];
  lang: Lang;
}) {
  const [page, setPage] = useState<{ limit: number; firstAdded: number | null }>({
    limit: PAGE_SIZE,
    firstAdded: null,
  });
  const addedEntry = useRef<HTMLLIElement>(null);
  const copy = (key: AuditMessage) => AUDITS_MESSAGES[key][lang];
  const visible = entries.slice(0, page.limit);
  const byEntity = new Map<string, RecurringEntry[]>();
  for (const entry of visible) {
    const group = byEntity.get(entry.entity);
    if (group) group.push(entry);
    else byEntity.set(entry.entity, [entry]);
  }

  useEffect(() => {
    if (page.firstAdded != null) addedEntry.current?.focus();
  }, [page]);

  return (
    <>
      <ul role='list' className='divide-y divide-neutral-border border-y border-neutral-border'>
        {Array.from(byEntity, ([entity, sections]) => (
          <li key={entity} className='min-w-0 space-y-2 px-3 py-3 [overflow-wrap:anywhere]'>
            <p className='font-semibold text-neutral-text'>{entity}</p>
            <ul role='list' className='space-y-2'>
              {sections.map(entry => (
                <li
                  key={entry.index}
                  ref={page.firstAdded === entry.index ? addedEntry : undefined}
                  tabIndex={-1}
                  className='flex min-w-0 flex-wrap items-baseline gap-x-4 gap-y-1 rounded text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-neutral-text'>
                  <span className='w-full min-w-0 text-neutral-text sm:w-56'>{auditSectionLabel(entry.section, lang)}</span>
                  {entry.years.length ? (
                    <ul role='list' className='flex min-w-0 flex-wrap gap-x-2 gap-y-1 sm:gap-x-3'>
                      {yearLabels.map(year => {
                        const recorded = entry.years.includes(year);
                        return (
                          <li key={year} className='relative flex items-center gap-1.5 text-neutral-text tabular-nums'>
                            {year} <span aria-hidden='true' className={markerClass(recorded)} />
                            <span className='sr-only'>
                              {copy(recorded ? 'audits.recurring_year_recorded' : 'audits.recurring_year_unrecorded')}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <span className='text-neutral-muted'>{copy('audits.recurring_no_year')}</span>
                  )}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <div className='flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2'>
        <p role='status' className='text-sm text-neutral-muted'>
          {copy('audits.recurring_count')
            .replace('{shown}', visible.length.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE'))
            .replace('{total}', entries.length.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE'))}
        </p>
        {entries.length > page.limit && (
          <button
            type='button'
            className='audit-control'
            onClick={() => setPage({
              limit: page.limit + PAGE_SIZE,
              firstAdded: entries[page.limit].index,
            })}>
            {copy('audits.recurring_more').replace('{count}', String(Math.min(PAGE_SIZE, entries.length - page.limit)))}
          </button>
        )}
      </div>
    </>
  );
}

export default function AuditRecurringFindings() {
  const { lang } = useLang();
  const copy = (key: AuditMessage) => AUDITS_MESSAGES[key][lang];
  const { data, isPending, isError, isFetching, refetch } = useRecurringFindings();
  const entries = (data?.recurring_findings ?? []).map((row, index): RecurringEntry => ({
    index,
    entity: row.county_name,
    section: row.query_type,
    years: Array.from(new Set(row.years_appeared.filter(year => Number.isSafeInteger(year) && year > 0))),
  })).sort((a, b) => a.entity.localeCompare(b.entity, 'en-KE') || a.section.localeCompare(b.section, 'en-KE'));
  const confirmed = entries.filter(entry => entry.years.length >= 2);
  const limited = entries.filter(entry => entry.years.length < 2);
  const yearLabels = Array.from(new Set(entries.flatMap(entry => entry.years))).sort((a, b) => a - b);

  return (
    <section aria-labelledby='audit-recurring-heading' className='min-w-0 space-y-3' data-audit-recurring>
      <h2 id='audit-recurring-heading' className='font-display text-xl text-neutral-text'>
        {copy('audits.recurring_findings')}
      </h2>
      {isPending && <p role='status' className='text-sm text-neutral-muted'>{copy('audits.recurring_loading')}</p>}
      {isError && (
        <div className='space-y-2 text-sm'>
          <p role='alert'>{copy(data ? 'audits.recurring_refresh_error' : 'audits.recurring_error')}</p>
          <button
            type='button'
            disabled={isFetching}
            onClick={() => void refetch({ cancelRefetch: false })}
            className='audit-control'>
            {copy(isFetching ? 'audits.recurring_loading' : 'audits.retry')}
          </button>
        </div>
      )}
      {data && (
        <>
          {entries.length > 0 && (
            <p className='text-sm leading-relaxed text-neutral-muted'>{copy('audits.recurring_scope')}</p>
          )}
          {yearLabels.length > 0 && (
            <p className='flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-neutral-muted'>
              <span className='inline-flex items-center gap-1.5'>
                <span aria-hidden='true' className={markerClass(true)} />
                {copy('audits.recurring_year_recorded')}
              </span>
              <span className='inline-flex items-center gap-1.5'>
                <span aria-hidden='true' className={markerClass(false)} />
                {copy('audits.recurring_year_unrecorded')}
              </span>
            </p>
          )}
          {confirmed.length ? (
            <RecurringGroups entries={confirmed} yearLabels={yearLabels} lang={lang} />
          ) : (
            <p lang={data.absent_reason ? 'en' : undefined} className='[overflow-wrap:anywhere] text-sm leading-relaxed text-neutral-muted'>
              {data.absent_reason || copy('audits.recurring_empty')}
            </p>
          )}
          {limited.length > 0 && (
            <div className='space-y-3'>
              <h3 className='text-base font-semibold text-neutral-text'>{copy('audits.recurring_limited_title')}</h3>
              <p className='text-sm leading-relaxed text-neutral-muted'>{copy('audits.recurring_limited_note')}</p>
              <RecurringGroups entries={limited} yearLabels={yearLabels} lang={lang} />
            </div>
          )}
        </>
      )}
      <a href='#audit-findings-heading' className='audit-receipt'>{copy('audits.recurring_browse')}</a>
    </section>
  );
}
