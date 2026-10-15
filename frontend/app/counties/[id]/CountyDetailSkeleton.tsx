'use client';

import { Skeleton } from '@/components/ui/Skeleton';
import { useLang } from '@/lib/i18n/LangProvider';
import styles from '../CountyExperience.module.css';
import TabSkeleton from './tabs/TabSkeleton';

/** Both streaming and query loading reserve the actual county header rows.
 * No name, period, grade or financial amount is inferred before data arrives. */
export default function CountyDetailSkeleton() {
  const { t } = useLang();
  return (
    <div className={styles.detail} role='status' aria-busy='true' aria-live='polite'>
      <div className={styles.container}>
        <div className={styles.backLinks} aria-hidden='true'>
          <span className={styles.loadingBackLink}><Skeleton className='h-4 w-28' /></span>
        </div>
        <header className={styles.detailHeader}>
          <div className={styles.detailIdentity}>
            <div>
              <p className={styles.eyebrow}>{t('county.hero.eyebrow')}</p>
              <h1>{t('county.page.title_fallback')}</h1>
              <p className={styles.detailDescription}>{t('county.page.subtitle')}</p>
              <p className={styles.detailDescription} aria-hidden='true'>
                <span className={styles.loadingCopy} />
              </p>
              <p className={styles.detailYear} aria-hidden='true'>
                <span className={styles.loadingYear} />
              </p>
            </div>
            <div className={styles.detailActions} aria-hidden='true'>
              <Skeleton className='h-[38px] w-[101px]' />
              <Skeleton className='h-8 w-8' />
              <div className={styles.detailGrades}>
                {[0, 1].map((i) => <div key={i} className={styles.gradeBadge}>
                  <Skeleton className='h-12 w-full' />
                  <Skeleton className='h-9 w-full' />
                </div>)}
              </div>
            </div>
          </div>
          <div className={styles.detailMetrics} aria-hidden='true'>
            {[0, 1, 2, 3, 4].map((i) => <div key={i}>
              <div className={styles.loadingMetric}><Skeleton className='h-8 w-28 max-w-full' /></div>
              <div className={styles.loadingMetricLabel}><Skeleton className='h-[18px] w-20 max-w-full' /></div>
            </div>)}
          </div>
        </header>
        <p className='sr-only'>{t('county.loading')}</p>
        <div className={styles.sectionNavigation} aria-hidden='true'>
          <p className={styles.sectionNavLabel}>{t('county.sections.label')}</p>
          <div className={styles.tabs}>
            {(['overview', 'money', 'budget_debt', 'audit_findings', 'accountability'] as const).map((tab) => (
              <button key={tab} disabled tabIndex={-1}>{t(`county.tab.${tab}`)}</button>
            ))}
          </div>
        </div>
        <div className={styles.reportBody} aria-hidden='true'><TabSkeleton /></div>
      </div>
    </div>
  );
}
