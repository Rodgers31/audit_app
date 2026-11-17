'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import type { LenderCategory } from '@/lib/debt/lenderBreakdown';
import { fmtKES } from '@/lib/utils';
import { ChevronDown } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import styles from './RankedLenders.module.css';

type LenderType = 'domestic' | 'external' | 'unclassified';

interface LenderGroup {
  type: LenderType;
  label: TranslationKey;
}

const KNOWN_GROUPS: ReadonlyMap<string, LenderGroup> = new Map<string, LenderGroup>([
  ['domestic_bonds', { type: 'domestic', label: 'debt.lenders.domestic_bonds' }],
  ['domestic_bills', { type: 'domestic', label: 'debt.lenders.domestic_bills' }],
  ['domestic_overdraft', { type: 'domestic', label: 'debt.lenders.domestic_overdraft' }],
  ['domestic_legacy', { type: 'domestic', label: 'debt.lenders.domestic_legacy' }],
  ['cbk_advance', { type: 'domestic', label: 'debt.lenders.cbk_advance' }],
  ['external_multilateral', { type: 'external', label: 'debt.lenders.external_multilateral' }],
  ['external_bilateral', { type: 'external', label: 'debt.lenders.external_bilateral' }],
  ['external_commercial', { type: 'external', label: 'debt.lenders.external_commercial' }],
  ['external_eurobond', { type: 'external', label: 'debt.lenders.external_eurobond' }],
  ['county_guaranteed', { type: 'unclassified', label: 'debt.lenders.county_guaranteed' }],
  ['other', { type: 'unclassified', label: 'debt.lenders.other_group' }],
]);

const VISIBLE_GROUPS = 5;
const isWorldBank = (name: string) => /\bWorld Bank\b/i.test(name);

function formatShare(share: number): string {
  if (share > 0 && share < 0.1) return '<0.1';
  const whole = Math.round(share);
  if (whole === 0 || (whole === 100 && share < 100) || (whole === 50 && share !== 50)) {
    const precise = share.toFixed(2).replace(/\.?0+$/, '');
    if (precise === '100' || precise === '50') return `${share < whole ? '<' : '>'}${whole}`;
    return precise;
  }
  return String(whole);
}

export default function RankedLenders({
  categories, totalOutstanding,
}: {
  categories: LenderCategory[];
  totalOutstanding: number;
}) {
  const { lang, t } = useLang();
  const headingId = useId();
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const firstAdditionalGroup = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (showAll) firstAdditionalGroup.current?.focus();
  }, [showAll]);
  const exact = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 2 });
  const formatExact = (amount: number) => `KES ${exact.format(amount)}`;

  const groups = categories.map((category) => {
    const known = KNOWN_GROUPS.get(category.category);
    const hasWorldBankAndOthers = category.category === 'external_multilateral' &&
      category.lenders.some(lender => isWorldBank(lender.lender)) &&
      category.lenders.some(lender => lender.lender && !isWorldBank(lender.lender));
    return {
      ...category,
      type: known?.type ?? 'unclassified',
      name: hasWorldBankAndOthers
        ? t('debt.lenders.multilateral_world_bank')
        : known ? t(known.label) : category.label,
    };
  }).sort((left, right) => right.outstanding - left.outstanding);
  const largest = groups[0];
  const totals = { domestic: 0, external: 0, unclassified: 0 };
  for (const group of groups) totals[group.type] += group.outstanding;
  const visible = showAll ? groups : groups.slice(0, VISIBLE_GROUPS);
  const moreCount = groups.length - VISIBLE_GROUPS;
  const usesPrincipal = groups.some(group => group.basis === 'principal');
  let takeaway: string | undefined;
  if (largest && totalOutstanding > 0) {
    const majority = usesPrincipal ? null : totals.domestic > totalOutstanding / 2 ? 'domestic'
      : totals.external > totalOutstanding / 2 ? 'external' : null;
    takeaway = majority
      ? t(`debt.lenders.${majority}_majority`).replace('{share}', formatShare(totals[majority] / totalOutstanding * 100))
      : t(usesPrincipal ? 'debt.lenders.largest_reported' : 'debt.lenders.largest').replace('{group}', () => largest.name)
          .replace('{share}', formatShare(largest.share));
  }

  return (
    <section className='min-w-0 space-y-3' aria-labelledby={headingId}>
      <h2 id={headingId} className='font-display text-2xl font-bold sm:text-3xl'>{t('debt.lenders.title')}</h2>
      {!largest ? <p className='text-sm text-neutral-muted'>{t('debt.lenders.empty')}</p> : (
        <>
          <p className='text-sm text-neutral-muted'>{takeaway}</p>
          {usesPrincipal && <p className='text-sm text-neutral-muted'>{t('debt.lenders.principal_scope')}</p>}
          <ul className={styles.legend}>
            {(['domestic', 'external', 'unclassified'] as const).filter(type => totals[type] > 0).map(type => (
              <li key={type}>
                <span className={styles.swatch} data-type={type} aria-hidden='true' />{t(`debt.lenders.${type}`)}
              </li>
            ))}
          </ul>
          <ol id={`${headingId}-groups`} className={styles.ranking}>
            {visible.map((group, index) => {
              const isOpen = openGroup === group.category;
              const detailsId = `${headingId}-group-${index}`;
              const lenders = [...group.lenders].sort(
                (left, right) => (right.outstanding ?? -1) - (left.outstanding ?? -1)
              );
              return (
                <li key={group.category}>
                  <button type='button' className={styles.row} aria-expanded={isOpen} aria-controls={detailsId}
                    ref={index === VISIBLE_GROUPS ? firstAdditionalGroup : undefined}
                    onClick={() => setOpenGroup(isOpen ? null : group.category)}>
                    <span className={styles.name}>{group.name}</span>
                    <span className={styles.amount}>{fmtKES(group.outstanding)}</span>
                    <span className={styles.track} aria-hidden='true'>
                      <span className={styles.bar} data-type={group.type}
                        style={{ width: `${group.outstanding / largest.outstanding * 100}%` }} />
                    </span>
                    <span className={styles.identity}>
                      {formatShare(group.share)}% · {t(`debt.lenders.${group.type}`)}
                      {group.basis === 'principal' && <> · {t('debt.lenders.principal')}</>}
                    </span>
                    <ChevronDown className={styles.chevron} size={16} aria-hidden='true' />
                  </button>
                  <div id={detailsId} hidden={!isOpen} className={styles.details}>
                    {isOpen && (
                      <>
                        <p className={styles.exactAmount}>{t('debt.lenders.amount')} · {formatExact(group.outstanding)}</p>
                        {lenders.length === 0 && !group.itemsTruncated ? (
                          <p className='text-sm text-neutral-muted'>{t('debt.lenders.details_missing')}</p>
                        ) : (
                          <ul className={styles.lenders}>
                            {lenders.map((lender, i) => (
                              <li key={`${lender.lender}-${i}`}>
                                <span>
                                  {lender.lender || t('debt.lenders.name_missing')}
                                  {lender.basis === 'principal' && lender.outstanding != null && (
                                    <span className='block text-xs text-neutral-muted'>{t('debt.lenders.principal')}</span>
                                  )}
                                </span>
                                <span>{lender.outstanding == null ? t('debt.lenders.amount_missing') : formatExact(lender.outstanding)}</span>
                              </li>
                            ))}
                            {group.itemsTruncated && (
                              <li>
                                <span>{group.otherLenderCount > 0
                                  ? t('debt.lenders.other_count').replace('{count}', exact.format(group.otherLenderCount))
                                  : t('debt.lenders.other')}</span>
                                <span>{group.otherOutstanding == null
                                  ? t('debt.lenders.amount_missing')
                                  : formatExact(group.otherOutstanding)}</span>
                              </li>
                            )}
                          </ul>
                        )}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {moreCount > 0 && (
            <button type='button' className='audit-control' aria-expanded={showAll}
              aria-controls={`${headingId}-groups`}
              onClick={() => setShowAll(!showAll)}>
              {showAll ? t('debt.lenders.show_less') : t('debt.lenders.show_more').replace('{count}', exact.format(moreCount))}
            </button>
          )}
          <div className='space-y-2 text-sm text-neutral-muted'>
            <p>
              {t(usesPrincipal ? 'debt.lenders.reported_total' : 'debt.lenders.total_basis')
                .replace('{total}', fmtKES(totalOutstanding))} {t('debt.lenders.pending')}
            </p>
            {totals.external > 0 && <p>{t('debt.lenders.ids')}</p>}
          </div>
        </>
      )}
    </section>
  );
}
