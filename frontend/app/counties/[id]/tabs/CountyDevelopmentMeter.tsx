'use client';

import InfoSheet from '@/components/ui/InfoSheet';
import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { useId } from 'react';
import type { countyDevelopmentShare } from './developmentShare';

const MEDIUM_TERM_MINIMUM = 30;
const PFM_ACT_SECTION = 'https://pdmo.treasury.go.ke/publications/128/download#page=99';

export default function CountyDevelopmentMeter({ share }: { share: ReturnType<typeof countyDevelopmentShare> }) {
  const { lang, t } = useLang();
  const heading = useId();
  const copy = (key: TranslationKey, values: Record<string, string>) =>
    t(key).replace(/\{(\w+)\}/g, (token, name) => values[name] ?? token);
  const legalReference = copy('county.budget.development_reference', { value: String(MEDIUM_TERM_MINIMUM) });
  const legalScope = copy('county.budget.development_legal_scope', { value: String(MEDIUM_TERM_MINIMUM) });
  const number = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const currency = (value: number) => `KES ${number.format(value)}`;
  const displayRate = share
    ? new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { style: 'percent', maximumFractionDigits: 1 }).format(share.rate / 100)
    : '';
  const shareLabel = copy('county.budget.development_share', { value: displayRate });
  const reportScope = share ? copy('county.budget.development_period', {
    period: share.period, start: formatAsAt(share.start, lang) ?? share.start, end: formatAsAt(share.end, lang) ?? share.end,
  }) : '';
  const sourceLabel = share?.publisher
    ? copy('foundation.source', { publisher: share.publisher })
    : t('foundation.sources');

  return (
    <section aria-labelledby={heading} className='audit-panel space-y-3 p-4' data-county-development>
      <h3 id={heading} className='font-display text-xl text-neutral-text'>{t('county.budget.development_split')}</h3>
      {share ? (
        <>
          <figure className='space-y-2'>
            <div className='grid grid-cols-[auto_1fr_auto] items-baseline gap-x-2 text-sm text-neutral-muted' aria-hidden='true'>
              <span>0%</span>
              <strong className='justify-self-center text-center text-neutral-text'>{shareLabel}</strong>
              <span>100%</span>
            </div>
            <div role='meter' aria-label={t('county.budget.development_meter_label')}
              aria-valuemin={0} aria-valuemax={100} aria-valuenow={share.rate} aria-valuetext={shareLabel}
              className='relative h-3 rounded-full bg-surface-sunken'>
              <span aria-hidden='true' className='block h-full rounded-full bg-neutral-muted' style={{ width: `${share.rate}%` }} />
              <span aria-hidden='true' className='absolute -top-1 bottom-[-4px] w-0.5 bg-neutral-text ring-1 ring-surface-base'
                style={{ left: `${MEDIUM_TERM_MINIMUM}%` }} />
            </div>
            <figcaption className='text-sm text-neutral-muted' style={{ paddingInlineStart: `${MEDIUM_TERM_MINIMUM}%` }}>
              {legalReference}
            </figcaption>
          </figure>
          <p className='text-sm text-neutral-muted'>{reportScope}</p>
          <p className='text-sm text-neutral-muted'>{legalScope}</p>
          <InfoSheet title={t('county.budget.development_receipt')} trigger={props => (
            <button {...props} type='button' className='audit-receipt text-left'
              aria-label={`${sourceLabel} · ${t('county.budget.development_receipt')}`}
              onClick={event => {
                event.currentTarget.focus({ preventScroll: true });
                props.onClick();
              }}>
              <span aria-hidden='true' className='size-2 shrink-0 bg-neutral-muted' />
              <span className='min-w-0 [overflow-wrap:anywhere]'>{sourceLabel}</span>
            </button>
          )}>
            <p>{reportScope}</p>
            <p>{copy('county.budget.development_values', {
              projects: currency(share.projects), operations: currency(share.operations), total: currency(share.total),
            })}</p>
            {share.sourceLinkedOnly && <p>{t('county.budget.development_source_limits')}</p>}
            <a href={share.href} target='_blank' rel='noopener noreferrer'
              className='flex min-h-11 items-center underline underline-offset-4 [overflow-wrap:anywhere]'>
              {share.sourceTitle || t('evidence.open_source')}
            </a>
            <p>{legalScope}</p>
            <a href={PFM_ACT_SECTION} target='_blank' rel='noopener noreferrer'
              className='flex min-h-11 items-center underline underline-offset-4 [overflow-wrap:anywhere]'>
              {t('county.budget.development_act')}
            </a>
          </InfoSheet>
        </>
      ) : <p className='text-sm text-neutral-muted'>{t('county.budget.development_missing')}</p>}
    </section>
  );
}
