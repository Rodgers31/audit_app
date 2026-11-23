'use client';

import InfoSheet from '@/components/ui/InfoSheet';
import StatCard, { type Signal } from '@/components/ui/StatCard';
import { formatAsAt, pendingBillsAbsenceLine, pendingBillsNoteLines } from '@/lib/counties/pendingBillsNotes';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_OVERVIEW_MESSAGES, COUNTY_TAB_LABELS } from '@/lib/i18n/messages/countyDetail';
import type { CountyComprehensive } from '@/types';
import type { ReactNode } from 'react';
import { fmtKES } from '../shared';
import { countyOverviewFacts, type OverviewSource } from './overviewFacts';

export type OverviewDestination = 'money' | 'budget' | 'audit';

function OverviewReceipt({ title, sources, children }: {
  title: string;
  sources: OverviewSource[];
  children: ReactNode;
}) {
  const { t } = useLang();
  const firstPublisher = sources[0]?.publisher;
  const publisher = sources.every(source => source.publisher === firstPublisher) ? firstPublisher : null;
  const label = publisher ? t('foundation.source').replace('{publisher}', () => publisher) : t('foundation.sources');
  return (
    <InfoSheet title={title} trigger={props => (
      <button {...props} type='button' className='audit-receipt text-left'
        aria-label={`${label} · ${title}`}
        onClick={event => {
          event.currentTarget.focus({ preventScroll: true });
          props.onClick();
        }}>
        <span aria-hidden='true' className='size-2 shrink-0 bg-neutral-muted' />
        <span className='min-w-0 [overflow-wrap:anywhere]'>{label}</span>
      </button>
    )}>
      {children}
      {sources.map(source => (
        <a key={source.href} href={source.href} target='_blank' rel='noopener noreferrer'
          className='flex min-h-11 items-center underline underline-offset-4 [overflow-wrap:anywhere]'>
          {source.title || t('evidence.open_source')}
        </a>
      ))}
    </InfoSheet>
  );
}

const SPENDING_TARGET = 70;

export default function OverviewHighlights({ data, onOpenTab }: {
  data: CountyComprehensive;
  onOpenTab?: (tab: OverviewDestination) => void;
}) {
  const { lang, t } = useLang();
  const copy = (key: keyof typeof COUNTY_OVERVIEW_MESSAGES, values: Record<string, string | number> = {}) =>
    COUNTY_OVERVIEW_MESSAGES[key][lang].replace(/\{(\w+)\}/g, (token, name) => String(values[name] ?? token));
  const { budgetSources, periodLabel, spending, pending, pendingShare, findingCounts } = countyOverviewFacts(data);
  const date = formatAsAt(pending?.asAt, lang);
  const number = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const exactCurrency = (amount: number) => `KES ${number.format(amount)}`;
  const percent = (rate: number, decimals: number) =>
    `${new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: decimals }).format(rate)}%`;
  const period = periodLabel ?? copy('period_unavailable');
  const spendVerdict = spending
    ? spending.rate > 100
      ? { signal: 'caution' as Signal, word: copy('above_allocation'), rule: copy('above_allocation_rule') }
      : spending.annual
        ? {
            signal: (spending.rate >= SPENDING_TARGET ? 'good' : 'caution') as Signal,
            word: copy(spending.rate >= SPENDING_TARGET ? 'on_track' : 'below_target'),
            rule: copy('annual_target', { target: SPENDING_TARGET }),
          }
        : {
            signal: 'context' as Signal,
            word: copy(spending.partYear ? 'part_year' : 'reporting_period'),
            rule: copy(spending.partYear ? 'part_year_rule' : 'period_rule'),
          }
    : null;
  const spendRate = spending
    ? spending.annual && spending.rate < SPENDING_TARGET && Math.round(spending.rate) === SPENDING_TARGET
      ? percent(Math.floor(spending.rate * 100) / 100, 2)
      : percent(spending.rate, spending.annual ? 0 : 1)
    : null;
  const { debt } = data;
  const pendingNotes = pendingBillsNoteLines(debt.pending_bills_notes, t, fmtKES);
  const pendingAbsent = pendingBillsAbsenceLine(debt.pending_bills_absence, lang, t);
  const auditPeriod = findingCounts?.period
    ? findingCounts.period.start === findingCounts.period.end
      ? String(findingCounts.period.start)
      : `${findingCounts.period.start}–${findingCounts.period.end}`
    : null;
  const auditSource = findingCounts ? [{ ...findingCounts.source, title: copy('audit_example'), publisher: copy('auditor_general') }] : [];

  function action(tab: OverviewDestination) {
    return onOpenTab && <button type='button' className='audit-control' onClick={() => onOpenTab(tab)}>
      {copy('see_tab', { tab: COUNTY_TAB_LABELS[tab][lang] })}
    </button>;
  }

  return (
    <section aria-labelledby='county-overview-heading' className='min-w-0 max-w-3xl space-y-3' data-county-overview>
      <h2 id='county-overview-heading' className='font-display text-xl text-neutral-text'>{copy('title')}</h2>
      <StatCard
        label={copy('spending')}
        value={spendRate}
        missingReason={copy('spending_missing')}
        comparison={spending
          ? copy('spending_compare', { spent: fmtKES(spending.spent), allocated: fmtKES(spending.allocated), period })
          : periodLabel}
        verdict={spendVerdict ? { ...spendVerdict, details: null } : undefined}
        source={<div className='flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1'>
          <OverviewReceipt title={copy('spending_source')} sources={budgetSources}>
            <p>{copy('spending_scope', { period })}</p>
            {spending && <p>
              {copy('spending_exact', {
                spent: exactCurrency(spending.spent), allocated: exactCurrency(spending.allocated),
                rate: percent(spending.rate, 4),
              })}
            </p>}
          </OverviewReceipt>
          {action('money')}
        </div>}
      />
      <StatCard
        label={copy('pending')}
        value={pending && date ? fmtKES(pending.amount) : null}
        missingReason={copy('pending_missing')}
        comparison={pending && date
          ? pendingShare
            ? copy('pending_compare', { share: percent(pendingShare.rate, 1), period })
            : copy('pending_no_share')
          : undefined}
        verdict={pending && date ? {
          signal: pending.amount > 0 ? 'caution' : 'context',
          word: copy(pending.amount > 0 ? 'watch' : 'zero_reported'),
          rule: copy('pending_date', { date }),
          details: null,
        } : undefined}
        source={<div className='flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1'>
          <OverviewReceipt title={copy('pending_source')} sources={pending && date ? [pending.source] : []}>
            <p>{t('counties.provenance.rest')}</p>
            {pending && date && <p>{copy('pending_exact', { amount: exactCurrency(pending.amount), date })}{pending.table ? ` · ${pending.table}` : ''}</p>}
            {pendingShare && <p>{copy('pending_denominator', { amount: exactCurrency(pendingShare.allocated), period })}</p>}
            {pendingAbsent && <p>{pendingAbsent}</p>}
            {pendingNotes.map(note => <p key={note}>{note}</p>)}
          </OverviewReceipt>
          {action('budget')}
        </div>}
      />
      <StatCard
        label={copy('serious')}
        value={findingCounts ? number.format(findingCounts.serious) : null}
        missingReason={copy('serious_missing')}
        comparison={findingCounts
          ? auditPeriod
            ? copy('audit_count_with_period', { count: number.format(findingCounts.total), period: auditPeriod })
            : copy('audit_count', { count: number.format(findingCounts.total) })
          : undefined}
        verdict={findingCounts ? {
          signal: findingCounts.serious > 0 ? 'alarm' : 'context',
          word: copy(findingCounts.serious > 0 ? 'serious_signal' : 'zero_reported'),
          rule: copy('serious_scope'),
          details: null,
        } : undefined}
        source={<div className='flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1'>
          <OverviewReceipt title={copy('audit_source')} sources={auditSource}>
            <p>{copy('audit_scope')}</p>
            {findingCounts && !auditPeriod && <p>{copy('audit_period_missing')}</p>}
          </OverviewReceipt>
          {action('audit')}
        </div>}
      />
    </section>
  );
}
