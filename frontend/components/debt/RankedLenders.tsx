'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { formatLenderShare, type LenderCategory } from '@/lib/debt/lenderBreakdown';
import { fmtKES } from '@/lib/utils';
import { ChevronDown } from 'lucide-react';
import { useId, useState } from 'react';
import DebtComposition, { type LenderType } from './DebtComposition';
import styles from './RankedLenders.module.css';

interface LenderGroup {
  type: LenderType;
  label: TranslationKey;
  color: string;
}

const FOREST = 'rgb(var(--c-accent-sage))';
const MUTED = 'rgb(var(--c-neutral-muted))';

const KNOWN_GROUPS: ReadonlyMap<string, LenderGroup> = new Map<string, LenderGroup>([
  ['domestic_bonds', { type: 'domestic', label: 'debt.lenders.domestic_bonds', color: FOREST }],
  ['domestic_bills', { type: 'domestic', label: 'debt.lenders.domestic_bills', color: 'var(--chart-teal)' }],
  ['domestic_overdraft', { type: 'domestic', label: 'debt.lenders.domestic_overdraft', color: 'var(--chart-blue)' }],
  ['domestic_legacy', { type: 'domestic', label: 'debt.lenders.domestic_legacy', color: 'color-mix(in srgb, var(--chart-blue) 65%, var(--chart-context))' }],
  ['cbk_advance', { type: 'domestic', label: 'debt.lenders.cbk_advance', color: 'color-mix(in srgb, var(--chart-teal) 55%, var(--chart-context))' }],
  ['external_multilateral', { type: 'external', label: 'debt.lenders.external_multilateral', color: 'var(--chart-gold)' }],
  ['external_bilateral', { type: 'external', label: 'debt.lenders.external_bilateral', color: 'var(--chart-clay)' }],
  ['external_commercial', { type: 'external', label: 'debt.lenders.external_commercial', color: MUTED }],
  ['external_eurobond', { type: 'external', label: 'debt.lenders.external_eurobond', color: 'color-mix(in srgb, var(--chart-clay) 60%, var(--chart-context))' }],
  ['county_guaranteed', { type: 'unclassified', label: 'debt.lenders.county_guaranteed', color: 'color-mix(in srgb, var(--chart-context) 70%, var(--chart-blue))' }],
  ['other', { type: 'unclassified', label: 'debt.lenders.other_group', color: 'var(--chart-context)' }],
]);
const GROUP_ORDER = Array.from(KNOWN_GROUPS.keys());
const isWorldBank = (name: string) => /\bWorld Bank\b/i.test(name);
const orderOf = (name: string) => {
  const index = GROUP_ORDER.indexOf(name);
  return index === -1 ? GROUP_ORDER.length : index;
};

function colorForUnknown(category: string) {
  const key = Array.from(category).reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) % 61, 0);
  return `color-mix(in srgb, var(--chart-context) ${20 + key}%, ${MUTED})`;
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
  const exact = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 2 });
  const formatExact = (amount: number) => `KES ${exact.format(amount)}`;

  const hasSeparateEurobonds = categories.some(category => category.category === 'external_eurobond');
  const groups = categories.map((category) => {
    const known = KNOWN_GROUPS.get(category.category);
    const hasWorldBankAndOthers = category.category === 'external_multilateral' &&
      category.lenders.some(lender => isWorldBank(lender.lender)) &&
      category.lenders.some(lender => lender.lender && !isWorldBank(lender.lender));
    const label = hasWorldBankAndOthers ? 'debt.lenders.multilateral_world_bank'
      : hasSeparateEurobonds && category.category === 'external_commercial' ? 'debt.lenders.commercial_only'
      : known?.label;
    return {
      ...category,
      type: known?.type ?? 'unclassified',
      color: known?.color ?? colorForUnknown(category.category),
      name: label ? t(label) : category.label,
    };
  }).sort((left, right) => orderOf(left.category) - orderOf(right.category) || left.category.localeCompare(right.category));
  const largest = groups.reduce<(typeof groups)[number] | undefined>((top, group) =>
    !top || group.outstanding > top.outstanding ? group : top, undefined);
  const totals = { domestic: 0, external: 0, unclassified: 0 };
  for (const group of groups) totals[group.type] += group.outstanding;
  const usesPrincipal = groups.some(group => group.basis === 'principal');
  let takeaway: string | undefined;
  if (largest && totalOutstanding > 0) {
    const majority = usesPrincipal ? null : totals.domestic > totalOutstanding / 2 ? 'domestic'
      : totals.external > totalOutstanding / 2 ? 'external' : null;
    takeaway = majority
      ? t(`debt.lenders.${majority}_majority`).replace('{share}', formatLenderShare(totals[majority] / totalOutstanding * 100))
      : t(usesPrincipal ? 'debt.lenders.largest_reported' : 'debt.lenders.largest').replace('{group}', () => largest.name)
          .replace('{share}', formatLenderShare(largest.share));
  }

  return (
    <section className='min-w-0 space-y-3' aria-labelledby={headingId}>
      <h2 id={headingId} className='font-display text-2xl font-bold sm:text-3xl'>{t('debt.lenders.title')}</h2>
      {!largest ? <p className='text-sm text-neutral-muted'>{t('debt.lenders.empty')}</p> : (
        <>
          <p className='text-sm text-neutral-muted'>{takeaway}</p>
          {usesPrincipal && <p className='text-sm text-neutral-muted'>{t('debt.lenders.principal_scope')}</p>}
          <DebtComposition groups={groups} total={totalOutstanding} usesPrincipal={usesPrincipal} active={openGroup} />
          <ol role='list' aria-label={t('debt.lenders.instruments')} className={styles.ranking}>
            {groups.map((group, index) => {
              const isOpen = openGroup === group.category;
              const detailsId = `${headingId}-group-${index}`;
              const lenders = [...group.lenders].sort(
                (left, right) => (right.outstanding ?? -1) - (left.outstanding ?? -1)
              );
              return (
                <li key={group.category} data-key={group.category}>
                  <button type='button' className={styles.row} aria-expanded={isOpen} aria-controls={detailsId}
                    onClick={() => setOpenGroup(isOpen ? null : group.category)}>
                    <span className={styles.key} aria-hidden='true' style={{ backgroundColor: group.color }}>
                      <span>{index + 1}</span>
                    </span>
                    <span className={styles.name}>{group.name}</span>
                    <span className={styles.amount}>{fmtKES(group.outstanding)}</span>
                    <span className={styles.identity}>
                      {formatLenderShare(group.share)}% · {t(`debt.lenders.${group.type}`)}
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
