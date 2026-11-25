'use client';

import { useDataFreshness } from '@/components/DataFreshnessBadge';
import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { evidenceUrl } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import type { Lang } from '@/lib/i18n/messages';
import { SOURCES_MESSAGES } from '@/lib/i18n/messages/sources';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ExternalLink } from 'lucide-react';
import { useState } from 'react';

interface SourceSummary {
  publisher: string;
  website?: string | null;
  document_count: number;
  downloaded_documents?: number;
  extracted_documents?: number;
  last_fetched: string | null;
  doc_types: Record<string, number>;
}

interface SourcesResponse {
  sources: SourceSummary[];
  total_documents: number;
}

interface TableHealth {
  table: string;
  label: string;
  row_count: number;
  source: string | null;
  attribution_status?: 'empty' | 'single_publisher' | 'mixed_publishers' | 'partial' | 'unresolved';
  attribution_basis?: 'coherent_observation_identity' | 'stored_document_links' | 'unavailable';
  represented_publishers?: { source_id: string; name: string; row_count: number }[];
  unresolved_source_rows?: number;
  status: string;
  age_days?: number | null;
  stale_after_days?: number | null;
}

interface HealthResponse {
  tables: TableHealth[];
}

type MessageKey = keyof typeof SOURCES_MESSAGES;
type FreshnessEntry = NonNullable<ReturnType<typeof useDataFreshness>['data']>['sources'][number];

function copy(lang: Lang, key: MessageKey, vars: Record<string, string> = {}) {
  return SOURCES_MESSAGES[key][lang].replace(/\{(\w+)\}/g, (token, name: string) => vars[name] ?? token);
}

function countText(value: number, lang: Lang) {
  return value.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE');
}

function rowCount(value: number, lang: Lang) {
  return copy(lang, value === 1 ? 'rowsOne' : 'rowsMany', { count: countText(value, lang) });
}

function recordedDate(iso: string | null, lang: Lang) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(iso)) return null;
  const stamp = Date.parse(iso);
  if (!Number.isFinite(stamp) || stamp > Date.now()) return null;
  const day = iso.slice(0, 10);
  const date = new Date(`${day}T00:00:00Z`);
  if (date.toISOString().slice(0, 10) !== day) return null;
  return date.toLocaleDateString(lang === 'sw' ? 'sw-KE' : 'en-GB', {
    timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric',
  });
}

const PUBLISHERS: readonly {
  name: string;
  aliases: readonly string[];
  description: MessageKey;
  code?: string;
  cadence?: MessageKey;
}[] = [
  {
    name: 'Controller of Budget',
    aliases: ['controller of budget', 'controller of budget (cob)', 'office of the controller of budget', 'office of the controller of budget (ocob)', 'cob', 'ocob'],
    description: 'cob', code: 'COB', cadence: 'cobCadence',
  },
  {
    name: 'Office of the Auditor-General',
    aliases: ['office of the auditor general', 'office of the auditor general (oag)', 'auditor general', 'oag'],
    description: 'oag', code: 'OAG', cadence: 'oagCadence',
  },
  {
    name: 'Central Bank of Kenya',
    aliases: ['central bank of kenya', 'central bank of kenya (cbk)', 'cbk'],
    description: 'cbk', code: 'CBK', cadence: 'cbkCadence',
  },
  {
    name: 'Kenya National Bureau of Statistics',
    aliases: ['kenya national bureau of statistics', 'kenya national bureau of statistics (knbs)', 'knbs'],
    description: 'knbs', code: 'KNBS',
  },
  {
    name: 'National Treasury',
    aliases: ['national treasury', 'the national treasury', 'kenya national treasury', 'national treasury kenya', 'national treasury of kenya'],
    description: 'treasury', code: 'Treasury',
  },
  {
    name: 'Commission on Revenue Allocation',
    aliases: ['commission on revenue allocation', 'cra'],
    description: 'cra', code: 'CRA',
  },
  {
    name: 'World Bank Open Data',
    aliases: ['world bank', 'world bank open data'],
    description: 'worldBank',
  },
];

const DOC_TYPES = new Map<string, MessageKey>([
  ['budget', 'budgets'], ['audit', 'audits'], ['report', 'reports'],
  ['loan', 'loans'], ['other', 'other'],
]);

const FREQUENCIES = new Map<string, MessageKey>([
  ['Quarterly', 'quarterly'], ['Annually', 'annually'], ['Monthly', 'monthly'],
]);

const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal-good';

function publisherGroups(sources: SourceSummary[]) {
  const groups = new Map<string, {
    name: string;
    metadata?: typeof PUBLISHERS[number];
    records: SourceSummary[];
  }>();
  sources.forEach((source) => {
    // Match named publishers only. Joint or unfamiliar names retain their manifest identity.
    const normalized = source.publisher.trim().toLowerCase().replace(/[-\u2010-\u2015]/g, ' ').replace(/\s+/g, ' ');
    const metadata = PUBLISHERS.find((publisher) => publisher.aliases.includes(normalized));
    const name = metadata?.name ?? source.publisher;
    const group = groups.get(name);
    if (group) group.records.push(source);
    else groups.set(name, { name, metadata, records: [source] });
  });
  return Array.from(groups.values()).sort((a, b) =>
    (a.metadata ? PUBLISHERS.indexOf(a.metadata) : PUBLISHERS.length) -
    (b.metadata ? PUBLISHERS.indexOf(b.metadata) : PUBLISHERS.length)
  );
}

function PublisherList({ sources, freshness, lang }: {
  sources: SourceSummary[];
  freshness: FreshnessEntry[];
  lang: Lang;
}) {
  return (
    <ul role='list' className='divide-y divide-neutral-border border-b border-neutral-border'>
      {publisherGroups(sources).map(({ name, metadata, records }) => {
        const recordedTypes = new Set<MessageKey>();
        const websites = new Set<string>();
        records.forEach((record) => {
          Object.entries(record.doc_types).forEach(([type, count]) => {
            if (count > 0) recordedTypes.add(DOC_TYPES.get(type) ?? 'unknownType');
          });
          const website = evidenceUrl(record.website);
          if (website) websites.add(website);
        });
        // Summary can return one partner's homepage for a joint manifest label.
        const href = websites.size === 1 && (metadata || !/[&/]/.test(name)) ? Array.from(websites)[0] : undefined;
        const description = metadata ? copy(lang, metadata.description)
          : Array.from(recordedTypes, (key) => copy(lang, key)).join(' · ') || copy(lang, 'unknownType');
        const matches = metadata?.code ? freshness.filter((entry) => entry.source === metadata.code) : [];
        const receipt = matches.length === 1 ? matches[0] : null;
        // The shared query returns the full response. These fields have no role in its badge.
        const period = receipt && 'covers_through' in receipt && typeof receipt.covers_through === 'string'
          ? receipt.covers_through.trim() : '';
        const frequency = receipt && 'update_frequency' in receipt && typeof receipt.update_frequency === 'string'
          ? FREQUENCIES.get(receipt.update_frequency) : undefined;
        const published = receipt ? recordedDate(receipt.last_updated, lang) : null;
        return (
          <li key={name} className='min-w-0 py-2 [overflow-wrap:anywhere]'>
            <h2 className='text-base font-bold text-neutral-text'>
              {href ? (
                <a href={href} target='_blank' rel='noopener noreferrer'
                  className={`inline-flex min-h-11 min-w-11 max-w-full items-center gap-2 rounded text-signal-good underline underline-offset-4 ${FOCUS}`}>
                  <span className='min-w-0'>{name}</span>
                  <ExternalLink size={15} className='shrink-0' aria-hidden='true' />
                </a>
              ) : <span className='flex min-h-11 items-center'>{name}</span>}
            </h2>
            <p className='text-sm leading-relaxed text-neutral-muted'>
              {description}
              {metadata?.cadence && frequency && <> · {copy(lang, metadata.cadence, { frequency: copy(lang, frequency) })}</>}
            </p>
            {period && <p className='text-audit-label text-neutral-muted'>{copy(lang, 'acceptedCoverage', { period })}</p>}
            {published && <p className='text-audit-label text-neutral-muted'>{copy(lang, 'acceptedPublication', { date: published })}</p>}
          </li>
        );
      })}
    </ul>
  );
}

const STATUS = new Map<string, { label: MessageKey; tone: string }>([
  ['healthy', { label: 'healthy', tone: 'text-signal-good' }],
  ['stale', { label: 'stale', tone: 'text-signal-caution' }],
  ['degraded', { label: 'degraded', tone: 'text-signal-caution' }],
  ['critical', { label: 'critical', tone: 'text-signal-alarm' }],
  ['empty', { label: 'empty', tone: 'text-neutral-muted' }],
]);

function attribution(table: TableHealth, lang: Lang) {
  switch (table.attribution_status) {
    case 'empty': return copy(lang, 'noAttribution');
    case 'mixed_publishers': return copy(lang, 'mixedAttribution');
    case 'partial': return copy(lang, 'partialAttribution');
    case 'unresolved': return copy(lang, 'unresolvedAttribution');
    case 'single_publisher': return copy(lang, table.attribution_basis === 'stored_document_links'
      ? 'linkedAttribution' : 'observationAttribution');
    default: return table.attribution_basis === 'stored_document_links' ? copy(lang, 'linkedAttribution')
      : table.source || copy(lang, 'attributionUnavailable');
  }
}

function RequestError({ message, retry, lang }: { message: string; retry: () => void; lang: Lang }) {
  return (
    <div className='flex flex-wrap items-center gap-x-3'>
      <p role='alert' className='text-sm text-signal-alarm'>{message}</p>
      <button type='button' onClick={retry}
        className={`min-h-11 min-w-11 rounded px-2 text-sm font-semibold text-signal-good underline ${FOCUS}`}>
        {copy(lang, 'retry')}
      </button>
    </div>
  );
}

function DataHealth({ lang }: { lang: Lang }) {
  const { data, isPending, isError, refetch } = useQuery<HealthResponse>({
    queryKey: ['provenance', 'health'],
    queryFn: async ({ signal }) => (await api.get<HealthResponse>('/provenance/health', { signal })).data,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  return (
    <div className='space-y-3 pt-3'>
      <p className='text-sm text-neutral-muted'>{copy(lang, 'healthIntro')}</p>
      <p className='text-sm text-neutral-muted'>{copy(lang, 'healthLineage')}</p>
      {isPending && <p role='status' className='text-sm text-neutral-muted'>{copy(lang, 'healthLoading')}</p>}
      {isError && <RequestError message={copy(lang, 'healthError')} retry={() => void refetch()} lang={lang} />}
      {data?.tables.length === 0 && <p className='text-sm text-neutral-muted'>{copy(lang, 'healthEmpty')}</p>}
      {data && data.tables.length > 0 && (
        <ul role='list' className='grid gap-2 sm:grid-cols-2 lg:grid-cols-3'>
          {data.tables.map((table) => {
            const status = STATUS.get(table.status);
            const age = table.age_days;
            const unresolvedRows = table.unresolved_source_rows;
            return (
              <li key={table.table} className='min-w-0 space-y-1 rounded border border-neutral-border p-3 [overflow-wrap:anywhere]'>
                <div className='flex flex-wrap items-baseline justify-between gap-x-2'>
                  <h3 className='text-sm font-bold text-neutral-text'>{table.label}</h3>
                  <span className={`text-audit-label font-semibold ${status?.tone ?? 'text-neutral-muted'}`}>
                    {copy(lang, status?.label ?? 'unknown')}
                  </span>
                </div>
                <p className='text-audit-label font-semibold text-neutral-text'>{rowCount(table.row_count, lang)}</p>
                <p className='text-audit-label text-neutral-muted'>{attribution(table, lang)}</p>
                {table.attribution_basis === 'stored_document_links' && (
                  <p className='text-audit-label text-neutral-muted'>{copy(lang, 'linkOnly')}</p>
                )}
                {table.represented_publishers?.map((publisher) => (
                  <p key={publisher.source_id} className='text-audit-label text-neutral-muted'>
                    {publisher.name} · {rowCount(publisher.row_count, lang)}
                  </p>
                ))}
                {unresolvedRows != null && unresolvedRows > 0 && (
                  <p className='text-audit-label text-neutral-muted'>
                    {copy(lang, 'unresolvedRows', { rows: rowCount(unresolvedRows, lang) })}
                  </p>
                )}
                <p className='flex flex-wrap gap-x-2 text-audit-label text-neutral-muted'>
                  {age != null && (
                    <span>{copy(lang, age === 0 ? 'changedToday' : age === 1 ? 'changedDay' : 'changedDays',
                      { count: countText(age, lang) })}</span>
                  )}
                  {table.stale_after_days != null && (
                    <span>{copy(lang, 'staleAfter', { count: countText(table.stale_after_days, lang) })}</span>
                  )}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function DocumentInventory({ sources, lang }: { sources: SourceSummary[]; lang: Lang }) {
  return (
    <div className='space-y-2 border-t border-neutral-border pt-3'>
      <h3 className='text-base font-bold text-neutral-text'>{copy(lang, 'inventory')}</h3>
      <p className='text-sm text-neutral-muted'>{copy(lang, 'inventoryIntro')}</p>
      <ul role='list' className='divide-y divide-neutral-border'>
        {sources.map((source) => {
          const date = recordedDate(source.last_fetched, lang);
          const registered = copy(lang, 'registered', { count: countText(source.document_count, lang) });
          const downloaded = source.downloaded_documents == null ? copy(lang, 'downloadCountUnavailable')
            : copy(lang, 'downloaded', { count: countText(source.downloaded_documents, lang) });
          const extracted = source.extracted_documents == null ? copy(lang, 'extractionCountUnavailable')
            : copy(lang, 'extracted', { count: countText(source.extracted_documents, lang) });
          return (
            <li key={source.publisher} className='space-y-1 py-2 text-audit-label text-neutral-muted [overflow-wrap:anywhere]'>
              <p className='text-sm font-semibold text-neutral-text'>{source.publisher}</p>
              <p>{registered} · {downloaded} · {extracted}</p>
              {Object.keys(source.doc_types).length > 0 && (
                <p>{Object.entries(source.doc_types).map(([type, count]) =>
                  `${copy(lang, DOC_TYPES.get(type) ?? 'unknownType')} (${countText(count, lang)})`).join(' · ')}</p>
              )}
              <p>{date ? copy(lang, 'checkedDownload', { date }) : copy(lang, 'noDownload')}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function SourcesPage() {
  const { lang } = useLang();
  const [healthRequested, setHealthRequested] = useState(false);
  const { data, isPending, isError, refetch } = useQuery<SourcesResponse>({
    queryKey: ['sources', 'summary'],
    queryFn: async ({ signal }) => (await api.get<SourcesResponse>('/sources/summary', { signal })).data,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  const freshness = useDataFreshness();

  return (
    <PageShell title={copy(lang, 'title')} subtitle={copy(lang, 'intro')} breadcrumbs={false}>
      <div className='space-y-6'>
        <section aria-label={copy(lang, 'publishers')}>
          {isPending && (
            <div className='divide-y divide-neutral-border' role='status'>
              <p className='sr-only'>{copy(lang, 'summaryLoading')}</p>
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index} aria-hidden='true' className='space-y-2 py-5'>
                  <div className='h-4 w-48 max-w-full rounded bg-surface-elevated' />
                  <div className='h-3 w-72 max-w-full rounded bg-surface-elevated' />
                </div>
              ))}
            </div>
          )}
          {isError && <RequestError message={copy(lang, 'summaryError')} retry={() => void refetch()} lang={lang} />}
          {data?.sources.length === 0 && (
            <p className='py-2 text-sm font-semibold text-neutral-text'>{copy(lang, 'emptyManifest')}</p>
          )}
          {data && data.sources.length > 0 && (
            <PublisherList sources={data.sources} freshness={freshness.isError ? [] : freshness.data?.sources ?? []} lang={lang} />
          )}
          {data && (
            <p className='mt-3 text-audit-label text-neutral-muted'>
              <span>{copy(lang, 'documentsIndexed')}</span> · <span className='font-mono'>{countText(data.total_documents, lang)}</span>
            </p>
          )}
        </section>

        <details className='group rounded border border-neutral-border bg-surface-base'
          onToggle={(event) => { if (event.currentTarget.open) setHealthRequested(true); }}>
          <summary className={`flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded px-3 py-2 text-sm font-semibold text-neutral-text [&::-webkit-details-marker]:hidden ${FOCUS}`}>
            {copy(lang, 'health')}
            <ChevronDown size={16} aria-hidden='true' className='shrink-0 text-neutral-muted group-open:rotate-180' />
          </summary>
          {healthRequested && (
            <div className='space-y-4 px-3 pb-3'>
              <h2 className='sr-only'>{copy(lang, 'health')}</h2>
              <DataHealth lang={lang} />
              {data && data.sources.length > 0 && <DocumentInventory sources={data.sources} lang={lang} />}
            </div>
          )}
        </details>

        <section className='space-y-2 border-t border-neutral-border pt-4' aria-labelledby='sources-method'>
          <h2 id='sources-method' className='text-base font-bold text-neutral-text'>{copy(lang, 'methodTitle')}</h2>
          <p className='max-w-[75ch] text-sm text-neutral-muted'>{copy(lang, 'method')}</p>
          <p className='max-w-[75ch] text-sm text-neutral-muted'>{copy(lang, 'countyMethod')}</p>
        </section>
      </div>
    </PageShell>
  );
}
