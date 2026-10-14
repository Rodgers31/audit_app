'use client';

import { PageSkeleton } from '@/components/ui/Skeleton';
import { useLang } from '@/lib/i18n/LangProvider';
import styles from '../CountyExperience.module.css';

/** Stream a data-free shell while the existing bounded SSR read is pending. */
export default function CountyDetailLoading() {
  const { t } = useLang();
  return (
    <div className={styles.detail}>
      <div className={styles.container}>
        <header className={styles.detailHeader}>
          <h1>{t('county.page.title_fallback')}</h1>
          <p className={styles.intro}>{t('county.loading')}</p>
        </header>
        <PageSkeleton />
      </div>
    </div>
  );
}
