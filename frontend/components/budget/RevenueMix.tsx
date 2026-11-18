'use client';

import ChartReadout from '@/components/charts/ChartReadout';
import { useLang } from '@/lib/i18n/LangProvider';
import { useEffect, useId, useRef, useState } from 'react';
import { compactRevenue, hasAmount, isTotal, revenuePublisher, revenueRanking, withheldResidual, type RevFy, type RevSource } from './RevenueMix.data';
import RevenueSourceSheet from './RevenueSourceSheet';
import styles from './RevenueMix.module.css';

export type { RevFy, RevSource } from './RevenueMix.data';

const MEASURES = {
  'Customs departmental collections, including agency levies': 'budget.revenue.customs',
  'Customs & Import Duty': 'budget.revenue.customs_legacy',
  'Domestic VAT': 'budget.revenue.vat',
  'Domestic excise': 'budget.revenue.excise',
  'Corporation Tax': 'budget.revenue.corporation',
} as const;

const DESCRIPTIONS = {
  'Customs & Import Duty': 'budget.revenue.desc_customs',
  PAYE: 'budget.revenue.desc_paye',
  VAT: 'budget.revenue.desc_vat',
  'Corporation Tax': 'budget.revenue.desc_corporation',
  'Excise Duty': 'budget.revenue.desc_excise',
} as const;

const BASIS = {
  published: 'budget.revenue.basis_published',
  derived: 'budget.revenue.basis_derived',
  residual: 'budget.revenue.basis_residual',
  projected: 'budget.revenue.basis_projected',
} as const;

export default function RevenueMix({ revenueBySource }: { revenueBySource: RevFy[] }) {
  const { lang, t } = useLang();
  const headingId = useId();
  const chart = useRef<HTMLOListElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (selected == null) return;
    function clearOutside(event: PointerEvent) {
      if (event.target instanceof Node && !chart.current?.contains(event.target)) {
        setPreview(null);
        setSelected(null);
      }
    }
    document.addEventListener('pointerdown', clearOutside);
    return () => document.removeEventListener('pointerdown', clearOutside);
  }, [selected]);

  const model = revenueRanking(revenueBySource);
  if (!model) return null;

  const { latest, ranked, releases } = model;
  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const whole = new Intl.NumberFormat(locale);
  const percent = new Intl.NumberFormat(locale, {
    style: 'percent', signDisplay: 'exceptZero', minimumFractionDigits: 1, maximumFractionDigits: 1,
  });
  const exact = (amount: number) => `KES ${whole.format(Math.round(amount * 1e9))}`;
  const label = (row: RevSource) => {
    const measure = row.measure?.trim() || row.revenue_type;
    const key = MEASURES[measure as keyof typeof MEASURES];
    return key ? t(key) : measure;
  };
  const basis = (row: RevSource) => {
    const key = BASIS[row.basis as keyof typeof BASIS];
    return key ? t(key) : t('budget.history.unconfirmed');
  };
  const growthLabel = (row: typeof ranked[number], short = false) => {
    if (!row.growth) return t('budget.revenue.growth_unavailable');
    const rate = percent.format(row.growth.amount / 100);
    if (short) return row.growth.basis === 'calculated' ? t('budget.revenue.growth_calculated_short').replace('{rate}', rate) : rate;
    return t(row.growth.basis === 'published' ? 'budget.revenue.growth_reported' : 'budget.revenue.growth_calculated')
      .replace('{rate}', rate);
  };
  const yearTakeaway = ranked.length && ranked[0].amount > 0
    ? t('budget.revenue.largest').replace('{head}', () => label(ranked[0])).replace('{amount}', compactRevenue(ranked[0].amount))
    : t(ranked.length ? 'budget.revenue.zero' : 'budget.revenue.empty_heads');
  const rowData = ranked.map(row => ({
    id: row.revenue_type,
    label: label(row),
    value: `${exact(row.amount)} · ${growthLabel(row)}${row.basis === 'published' ? '' : ` · ${basis(row)}`}`,
  }));
  const kra = ranked.length > 0 && ranked.every(row => row.basis === 'published' && revenuePublisher(row) === 'KRA');
  const period = t(kra ? 'budget.revenue.kra_period' : 'budget.revenue.period').replace('{year}', latest.fiscal_year);
  const missing = latest.sources.filter(row => !isTotal(row) && !withheldResidual(row) && !hasAmount(row)).map(label);

  return (
    <section aria-labelledby={headingId} className='min-w-0 space-y-2'>
      <h2 id={headingId} className='font-display text-2xl font-bold sm:text-3xl'>{t('budget.revenue.title')}</h2>
      <ChartReadout takeaway={`${period} ${yearTakeaway}`} activeId={preview ?? selected}
        columns={[t('budget.revenue.tax_head'), t('budget.revenue.amount_growth')]} data={rowData}>
        {missing.length > 0 && <p className='text-sm text-neutral-muted'>
          {t('budget.revenue.missing_heads').replace('{heads}', () => new Intl.ListFormat(locale).format(missing))}
        </p>}
        <ol ref={chart} role='list' className='m-0 list-none p-0'>
          {ranked.map((row, index) => {
            const datum = rowData[index];
            const exactId = `${headingId}-exact-${index}`;
            const descriptionKey = DESCRIPTIONS[row.revenue_type as keyof typeof DESCRIPTIONS];
            const description = row.basis && row.basis !== 'published' && row.basis_note
              ? row.basis_note.replace(/^(Derived|Residual|Projected)\s*:\s*/i, '')
              : descriptionKey ? t(descriptionKey) : null;
            return (
              <li key={datum.id} data-revenue-card data-basis={row.basis ?? undefined}>
                <button type='button' className={styles.row} aria-describedby={exactId}
                  aria-pressed={selected === datum.id} data-highlighted={(preview ?? selected) === datum.id}
                  onFocus={() => setPreview(datum.id)} onBlur={() => setPreview(null)}
                  onPointerEnter={event => { if (event.pointerType === 'mouse') setPreview(datum.id); }}
                  onPointerLeave={event => { if (event.pointerType === 'mouse') setPreview(null); }}
                  onClick={() => { setPreview(null); setSelected(current => current === datum.id ? null : datum.id); }}
                  onKeyDown={event => { if (event.key === 'Escape') { setPreview(null); setSelected(null); } }}>
                  <span className={styles.name}>{datum.label}</span>
                  <span className={styles.amount}>{compactRevenue(row.amount)}</span>
                  {row.amount > 0 && <span className={styles.bar} aria-hidden='true'>
                    <span style={{ width: `${row.amount / ranked[0].amount * 100}%` }} />
                  </span>}
                  <span className={styles.description}>{growthLabel(row, true)}{description && <> · {description}</>}
                    {row.basis !== 'published' && <> · {basis(row)}</>}
                  </span>
                </button>
                <span id={exactId} hidden>{datum.value}</span>
              </li>
            );
          })}
        </ol>
        <p className='text-sm text-neutral-muted'>{t('budget.revenue.scope')}</p>
        <RevenueSourceSheet latest={latest} releases={releases} label={label} basis={basis} exact={exact} />
      </ChartReadout>
    </section>
  );
}
