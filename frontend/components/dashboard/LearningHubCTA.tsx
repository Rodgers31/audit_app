'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { motion } from 'framer-motion';
import Link from 'next/link';

/**
 * Zone 8: Learning Hub CTA Section
 * Transparent background — the ScenicBackgroundLayout's bottom image shows through.
 * Content is white text for contrast against the cinematic bottom landscape.
 */
export default function LearningHubCTA() {
  const { t } = useLang();
  return (
    <section className='relative overflow-hidden py-12 sm:py-16'>
      <div className='relative z-10 max-w-2xl mx-auto text-center px-6'>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.7, delay: 0.1 }}>
          <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white mb-3 leading-tight'>
            {t('home.learning.heading')}
          </h2>
          <p className='text-sm sm:text-base text-gray-600 dark:text-neutral-muted mb-6 leading-relaxed'>
            {t('home.learning.body_prefix')}{' '}
            <span className='font-semibold text-gov-forest dark:text-emerald-100'>{t('home.learning.hub_name')}</span>.
          </p>
          <Link href='/learn'>
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className='btn-primary text-base px-8 py-3 rounded-xl'>
              {t('home.learning.visit')}
            </motion.button>
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
