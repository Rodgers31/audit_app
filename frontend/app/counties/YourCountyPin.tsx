'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_PIN_MESSAGES } from '@/lib/i18n/messages/countyExplorer';
import type { County } from '@/types';
import Link from 'next/link';
import { useSyncExternalStore } from 'react';
import { canonicalCounty, readLastViewedCounty, readServerCounty, subscribeLastViewedCounty } from './lastViewedCounty';
import styles from './YourCountyPin.module.css';

export default function YourCountyPin({ counties, fiscalYear, spendingRate }: {
  counties: County[];
  fiscalYear?: string;
  spendingRate: (county: County, fiscalYear?: string) => number | undefined;
}) {
  const { lang } = useLang();
  const pinned = useSyncExternalStore(subscribeLastViewedCounty, readLastViewedCounty, readServerCounty);
  if (!pinned) return null;

  const currentCounty = counties.find(county => canonicalCounty(county.name)?.slug === pinned.slug);
  const rate = currentCounty && spendingRate(currentCounty, fiscalYear);
  const periodQuery = currentCounty && fiscalYear ? `?fy=${encodeURIComponent(fiscalYear)}` : '';
  const percentage = rate?.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 1 });

  return (
    <Link href={`/counties/${pinned.slug}${periodQuery}`} className={styles.pin} prefetch={false}>
      <span className={styles.label}>{COUNTY_PIN_MESSAGES.label[lang]}</span>
      <strong>{pinned.name}</strong>
      {percentage != null && <span className={styles.metric}>{COUNTY_PIN_MESSAGES.spent[lang].replace('{rate}', percentage)}</span>}
    </Link>
  );
}
