'use client';

import ChartReadout from '@/components/charts/ChartReadout';
import InfoSheet from '@/components/ui/InfoSheet';
import { countyMoneyAmounts, countySpendShare } from '@/components/county/countyMoneyFlow';
import styles from '@/components/county/CountyMoneyFlow.module.css';
import { evidenceUrl } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_MONEY_MESSAGES } from '@/lib/i18n/messages/countyDetail';
import { fmtKES } from '@/lib/utils';
import { MoneyFlowData } from '@/types';
import { useEffect, useId, useRef, useState, type MouseEvent, type PointerEvent as ReactPointerEvent } from 'react';
import { auditAmountCoverageNote } from './transparency/moneyFlowPresentation';

export default function FollowTheMoney({ data, isLoading, findingsCount, onOpenAudit }: {
  data: MoneyFlowData | undefined;
  isLoading?: boolean;
  findingsCount?: number;
  onOpenAudit?: () => void;
}) {
  const { lang, t } = useLang();
  const words = (key: keyof typeof COUNTY_MONEY_MESSAGES) => COUNTY_MONEY_MESSAGES[key][lang];
  const chart = useRef<HTMLDivElement>(null);
  const helpId = useId();
  const [preview, setPreview] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const active = preview ?? selected;

  useEffect(() => {
    if (!selected) return;
    const clear = (event: PointerEvent) => {
      if (event.target instanceof Node && !chart.current?.contains(event.target)) {
        setPreview(null);
        setSelected(null);
      }
    };
    document.addEventListener('pointerdown', clear);
    return () => document.removeEventListener('pointerdown', clear);
  }, [selected]);

  if (isLoading) return <p role='status' className='py-8 text-sm text-neutral-muted'>{t('county.money.loading_read')}</p>;
  if (!data?.stages?.length) return <p role='status' className='py-8 text-sm text-neutral-muted'>{t('county.money.empty')}</p>;

  const values = countyMoneyAmounts(data);
  const { allocated, spent, unspent, overspent, ratio, committed, flagged, chartable, scale } = values;
  const number = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 2 });
  const exact = (value: number | null) => value == null || !Number.isFinite(value) ? null : `KES ${number.format(value)}`;
  const amount = (value: number | null) => {
    if (value == null) return t('foundation.no_chart_value');
    const absolute = Math.abs(value);
    return absolute >= 1e9 && absolute < 1e12 ? `KES ${(value / 1e9).toFixed(2)}B` : fmtKES(value);
  };
  const year = data.fiscal_year;
  let takeaway = words('unavailable_verdict').replace('{year}', year);
  if (overspent != null && allocated != null && allocated >= 0 && spent != null && spent >= 0) {
    takeaway = words('overspend_verdict').replace('{amount}', amount(overspent)).replace('{year}', year);
  } else if (ratio != null) {
    takeaway = words('verdict').replace('{county}', data.county_name).replace('{share}', countySpendShare(ratio)).replace('{year}', year);
  } else if (allocated === 0 && spent === 0) {
    takeaway = words('zero_verdict').replace('{year}', year);
  }
  const entries = [
    { id: 'allocated', label: words('allocated'), value: exact(allocated) },
    { id: 'spent', label: words('spent'), value: exact(spent) },
    { id: overspent == null ? 'unspent' : 'overspent', label: words(overspent == null ? 'unspent' : 'overspent'), value: exact(overspent ?? unspent) },
    { id: 'committed', label: words('committed'), value: exact(committed) },
    { id: 'flagged', label: words('flagged'), value: exact(flagged) },
  ];
  if (typeof data.total_waste_estimate === 'number' && Number.isFinite(data.total_waste_estimate) && data.total_waste_estimate !== flagged) {
    entries.push({ id: 'audit_subtotal', label: words('audit_subtotal'), value: exact(data.total_waste_estimate) });
  }
  const coverage = data.audit_amount_coverage ?? data.stages.find(stage => stage.stage === 'Flagged')?.amount_coverage;
  const coverageNote = coverage?.reason === 'no_findings'
    ? words('no_findings').replace('{year}', year) : auditAmountCoverageNote(coverage, lang);
  const source = data.source_document_title || data.stages.find(stage => stage.stage === 'Allocated')?.source;
  const sourceUrl = evidenceUrl(data.source_document_url) ??
    evidenceUrl(data.stages.find(stage => stage.stage === 'Allocated')?.source_doc);
  const bottomIds = unspent != null && unspent > 0 ? ['spent', 'unspent'] : ['spent'];

  const toggle = (id: string) => {
    setPreview(null);
    setSelected(current => current === id ? null : id);
  };
  const bottomAt = (event: MouseEvent<HTMLButtonElement> | ReactPointerEvent<HTMLButtonElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return spent != null && scale != null && (event.clientX - bounds.left) / bounds.width > spent / scale
      && unspent != null && unspent > 0 ? 'unspent' : 'spent';
  };

  return (
    <div className='min-w-0 space-y-3'>
      <ChartReadout takeaway={takeaway} columns={[words('flow'), words('amount')]} data={entries} activeId={active}>
        {chartable && scale != null && allocated != null && spent != null && (
          <div ref={chart} className={styles.flow} onKeyDown={event => {
            if (event.key === 'Escape') { setPreview(null); setSelected(null); }
          }}>
            <button type='button' className={styles.row} aria-pressed={selected === 'allocated'}
              data-highlighted={active === 'allocated'}
              onFocus={() => setPreview('allocated')} onBlur={() => setPreview(null)}
              onPointerEnter={event => { if (event.pointerType === 'mouse') setPreview('allocated'); }}
              onPointerLeave={event => { if (event.pointerType === 'mouse') setPreview(null); }}
              onClick={() => toggle('allocated')}>
              <span className={styles.rowLabel}>{words('allocated')} {amount(allocated)}</span>
              <span className={styles.track} aria-hidden='true'>
                <span className={styles.allocation} style={{ width: `${allocated / scale * 100}%` }} />
              </span>
            </button>
            <span id={helpId} className='sr-only'>{words('arrows')}</span>
            <button type='button' className={styles.row}
              data-overspent={overspent != null || undefined}
              aria-describedby={helpId} aria-pressed={selected === 'spent' || selected === 'unspent'}
              data-highlighted={active === 'spent' || active === 'unspent'}
              onFocus={() => setPreview(selected === 'unspent' ? 'unspent' : 'spent')} onBlur={() => setPreview(null)}
              onPointerMove={event => { if (event.pointerType === 'mouse') setPreview(bottomAt(event)); }}
              onPointerLeave={event => { if (event.pointerType === 'mouse') setPreview(null); }}
              onClick={event => toggle(event.detail === 0 ? (preview === 'unspent' ? 'unspent' : 'spent') : bottomAt(event))}
              onKeyDown={event => {
                if (['ArrowLeft', 'Home', 'ArrowRight', 'End'].includes(event.key)) {
                  event.preventDefault();
                  setPreview(event.key === 'ArrowLeft' || event.key === 'Home' ? 'spent' : bottomIds[bottomIds.length - 1]);
                }
              }}>
              <span className={styles.rowLabel}>{words('spent')} {amount(spent)}{ratio != null && ` (${countySpendShare(ratio)}%)`}</span>
              <span className={styles.track} aria-hidden='true'>
                <span className={styles.spent} style={{ width: `${spent / scale * 100}%` }} />
                {unspent != null && unspent > 0 && <span className={styles.gap} style={{ width: `${unspent / scale * 100}%` }} />}
              </span>
              <span className={styles.gapLabel}>{words(overspent == null ? 'unspent' : 'overspent')} {amount(overspent ?? unspent)}</span>
            </button>
          </div>
        )}
        {(allocated != null && allocated < 0 || spent != null && spent < 0) &&
          <p className={styles.detail}>{words('signed')}</p>}
        {unspent != null && <p className={styles.detail}>{words('unspent_note')}</p>}
      </ChartReadout>

      <div className={styles.detail}>
        {committed != null && <p>{words('committed')} {amount(committed)}. {words('commitment_short')}</p>}
        {coverageNote && <p>{coverageNote}</p>}
        {flagged != null && <p>{words('selected_period').replace('{year}', year)} · {amount(flagged)}. {words('audit_caveat')}</p>}
        {typeof findingsCount === 'number' && Number.isInteger(findingsCount) && findingsCount >= 0 &&
          <p>{words('aggregate').replace('{count}', number.format(findingsCount))}</p>}
        {onOpenAudit && <button type='button' onClick={onOpenAudit} className='audit-receipt'>{words('audit_link')}</button>}
      </div>

      <InfoSheet title={words('source')} trigger={props => (
        <button {...props} type='button' className='audit-receipt text-left' data-figure-evidence='county money flow'
          onClick={event => { event.currentTarget.focus(); props.onClick(); }}>
          <span className='h-2 w-2 shrink-0 rounded-full bg-neutral-muted' aria-hidden='true' />
          {source ? words('source_chip').replace('{source}', source) : words('source_unknown')}
        </button>
      )}>
        <p>{words('source_note')}</p>
        <p>{year} · {data.budget_source || t('budget.history.unconfirmed')}</p>
        {source && <p>{source}</p>}
        {sourceUrl && <a href={sourceUrl} target='_blank' rel='noopener noreferrer' className='inline-flex min-h-11 items-center underline'>{source || t('evidence.open_source')}</a>}
        <details>
          <summary className='min-h-11 cursor-pointer py-3 font-semibold'>{t('foundation.technical_details')}</summary>
          {data.stages.map(stage => {
            const link = evidenceUrl(stage.source_doc);
            return <div key={stage.stage} className='space-y-1 border-b border-neutral-border py-2'>
              <p>{stage.label} · {stage.data_unavailable ? t('foundation.no_chart_value') : exact(stage.amount) ?? t('foundation.no_chart_value')}</p>
              {stage.source && <p>{stage.source}</p>}
              {link && <a href={link} target='_blank' rel='noopener noreferrer' className='inline-flex min-h-11 items-center underline'>{t('evidence.open_source')}</a>}
              {stage.gap_from_prev != null && <p>{stage.gap_label} · {exact(stage.gap_from_prev)}</p>}
              {stage.amount_coverage && <p>{auditAmountCoverageNote(stage.amount_coverage, lang)}</p>}
              {stage.amount_coverage?.reason && <p>{stage.amount_coverage.reason.replace(/_/g, ' ')}</p>}
              {stage.amount_coverage && stage.amount_coverage.withheld_findings > 0 && <p>{words('withheld').replace('{count}', number.format(stage.amount_coverage.withheld_findings))}</p>}
            </div>;
          })}
          {committed != null && <p>{words('committed')} · {exact(committed)}. {words('commitment_note')}</p>}
          {coverageNote && <p>{coverageNote}</p>}
          {coverage?.reason && <p>{coverage.reason.replace(/_/g, ' ')}</p>}
          {coverage && coverage.withheld_findings > 0 && <p>{words('withheld').replace('{count}', number.format(coverage.withheld_findings))}</p>}
        </details>
      </InfoSheet>
    </div>
  );
}

export function YearSelector({ value, onChange, years }: {
  value: string;
  onChange: (year: string) => void;
  years: string[];
}) {
  const { lang } = useLang();
  return (
    <select value={value} onChange={event => onChange(event.target.value)}
      aria-label={COUNTY_MONEY_MESSAGES.period[lang]} className='audit-control max-w-full bg-surface-base'>
      {years.map(year => <option key={year} value={year}>FY {year.replace(/^FY\s*/i, '')}</option>)}
    </select>
  );
}
