/**
 * Side-by-side county comparison
 *
 * Compare county budgets, spending, debt and published audit findings. The goal is to let citizens ask
 * "how does my county compare to a similar-sized neighbor?" without having
 * to click through two detail pages and hold numbers in their head.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import { getCountyList } from '@/lib/api/counties';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_COMPARE_MESSAGES } from '@/lib/i18n/messages/countyCompare';
import { compareCountiesKey } from '@/lib/react-query/useCounties';
import { SSR_HYDRATED_STALE_TIME_MS } from '@/lib/react-query/isr';
import { useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useMemo, useState, Suspense } from 'react';
import CompareLedger from './CompareLedger';
import ComparePicker from './ComparePicker';
import { comparisonHref, MAX_COMPARE_COUNTIES, type CountySummary } from './ledgerData';

/**
 * The county list, behind one key shared by `CompareContent` and
 * `CompareFallback`.
 *
 * `app/counties/compare/page.tsx` prefetches this exact key on the server, so
 * the boundary's fallback and content use the same list for suggested pairs.
 */
export function useCompareCounties() {
  return useQuery<CountySummary[]>({
    queryKey: compareCountiesKey(),
    queryFn: ({ signal }) => getCountyList<CountySummary>({ limit: 50 }, signal),
    staleTime: SSR_HYDRATED_STALE_TIME_MS, // read from SSR state; see ./isr
  });
}

/** Shown until two counties are picked — static copy, no data. */
function CompareEmptyState() {
  const { t } = useLang();
  return (
    <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-12 text-center'>
      <div className='text-base font-semibold text-gray-700 dark:text-neutral-muted mb-1'>
        {t('compare.empty.title')}
      </div>
    </div>
  );
}

const EMPTY_SLOTS = ['', ''];

function CompareFallback() {
  const { data } = useCompareCounties();
  return (
    <div className='space-y-6'>
      <ComparePicker all={data ?? []} selected={EMPTY_SLOTS} disabled />
      <CompareEmptyState />
    </div>
  );
}

function CompareContent() {
  const { t } = useLang();
  const router = useRouter();
  const params = useSearchParams();
  const [selected, setSelected] = useState(() => {
    const uniqueIds = new Set(params.get('ids')?.split(',').filter(Boolean));
    const slots = Array.from(uniqueIds).slice(0, MAX_COMPARE_COUNTIES);
    while (slots.length < 2) slots.push('');
    return slots;
  });

  const { data: all, isLoading, error, refetch } = useCompareCounties();
  const byId = useMemo(() => new Map(all?.map((county) => [county.id, county])), [all]);
  const picked = selected.flatMap((id) => {
    const county = byId.get(id);
    return county ? [county] : [];
  });

  const updateSelected = (next: string[]) => {
    setSelected(next);
    router.replace(comparisonHref(next), { scroll: false });
  };

  const onChange = (index: number, countyId: string) => {
    if (countyId && (!byId.has(countyId) || selected.includes(countyId))) return;
    updateSelected(selected.map((id, slot) => slot === index ? countyId : id));
  };
  const onAdd = () => setSelected((ids) => ids.length < MAX_COMPARE_COUNTIES ? [...ids, ''] : ids);
  const onRemove = (index: number) =>
    updateSelected(selected.filter((_, slot) => slot !== index));

  return (
    <div className='space-y-6'>
      {isLoading && (
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 flex items-center justify-center gap-3 text-gray-500 dark:text-neutral-muted/80'>
          <Loader2 className='animate-spin' size={18} />
          <span>{t('compare.loading')}</span>
        </div>
      )}

      {error && (
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 text-center space-y-3'>
          <p role='alert'>{t('counties.error.title')}</p>
          <button type='button' onClick={() => refetch()} className='rounded-lg bg-gov-forest text-white px-4 py-3'>
            {t('counties.header.retry')}
          </button>
        </div>
      )}

      {!isLoading && !error && all && (
        <>
          <ComparePicker
            all={all}
            selected={selected}
            onChange={onChange}
            onPair={updateSelected}
            onAdd={onAdd}
            onRemove={onRemove}
          />

          {picked.length < 2 ? <CompareEmptyState /> : <CompareLedger counties={picked} />}
        </>
      )}
    </div>
  );
}

export default function ComparePage() {
  return <ComparePageInner />;
}

function ComparePageInner() {
  const { lang, t } = useLang();
  return (
    <PageShell
      title={t('compare.title')}
      subtitle={COUNTY_COMPARE_MESSAGES.subtitle[lang]}
      back={{ href: '/counties', label: t('common.all_counties') }}>
      {/*
        The Suspense boundary sits HERE, not around the whole page.
        `CompareContent` calls `useSearchParams()`, which on a statically
        prerendered route opts its subtree out of server rendering; the
        boundary is what scopes that bailout, so whatever it wraps is all the
        prerendered document can contain. It used to wrap `ComparePageInner` —
        PageShell and every heading with it — behind an 84px spinner, so the
        served HTML was the nav, an 84px box and the footer, and the footer
        then got shoved from y=84 to y=988 the moment the client rendered the
        page. One layout shift, 0.269, on a 0.1 budget (#221 finding #6).

        PageShell does not read the URL, so it is outside the boundary and
        server-renders. `CompareFallback` reserves the height of the state the
        unselected page opens in.
      */}
      <Suspense fallback={<CompareFallback />}>
        <CompareContent />
      </Suspense>
    </PageShell>
  );
}
