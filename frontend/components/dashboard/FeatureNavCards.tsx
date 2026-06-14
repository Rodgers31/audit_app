'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { motion } from 'framer-motion';
import { BarChart3, Globe, Map, Search } from 'lucide-react';
import Link from 'next/link';

type Accent = 'forest' | 'gold' | 'teal' | 'copper';

interface Feature {
  titleKey: TranslationKey;
  subKey: TranslationKey;
  icon: typeof Globe;
  href: string;
  accent: Accent;
}

/** Per-card accent so the nav strip carries colour + aids recognition. */
const ACCENTS: Record<Accent, { icon: string; bg: string }> = {
  forest: { icon: 'text-gov-forest dark:text-emerald-100', bg: 'bg-gov-forest/10 group-hover:bg-gov-forest/20' },
  gold: { icon: 'text-gov-gold', bg: 'bg-gov-gold/10 group-hover:bg-gov-gold/20' },
  teal: { icon: 'text-[#0D7377] dark:text-teal-300', bg: 'bg-[#0D7377]/10 group-hover:bg-[#0D7377]/20' },
  copper: { icon: 'text-gov-copper', bg: 'bg-gov-copper/10 group-hover:bg-gov-copper/20' },
};

const features: Feature[] = [
  { titleKey: 'home.features.debt.title', subKey: 'home.features.debt.sub', icon: Globe, href: '/debt', accent: 'forest' },
  { titleKey: 'home.features.budget.title', subKey: 'home.features.budget.sub', icon: BarChart3, href: '/budget', accent: 'gold' },
  { titleKey: 'home.features.explore.title', subKey: 'home.features.explore.sub', icon: Map, href: '/counties', accent: 'teal' },
  { titleKey: 'home.features.audits.title', subKey: 'home.features.audits.sub', icon: Search, href: '/audits', accent: 'copper' },
];

/**
 * Zone 7: Feature Navigation Strip
 * Four light navigation surfaces — NOT dashboard widgets.
 * Hover → slight elevation lift.
 */
export default function FeatureNavCards() {
  const { t } = useLang();
  return (
    <div className='grid grid-cols-2 lg:grid-cols-4 gap-4'>
      {features.map((feat, i) => (
        <motion.div
          key={feat.titleKey}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-40px' }}
          transition={{ duration: 0.5, delay: 0.08 * i }}>
          <Link href={feat.href}>
            <div
              className='group relative bg-white/70 dark:bg-surface-elevated backdrop-blur-sm border border-neutral-border/40 rounded-2xl p-5 sm:p-6 text-center
                            transition-all duration-300
                            hover:shadow-elevated hover:-translate-y-1 hover:border-gov-sage/30
                            cursor-pointer'>
              {/* Icon */}
              <div
                className={`w-12 h-12 mx-auto mb-3 rounded-xl flex items-center justify-center
                              transition-colors duration-300 ${ACCENTS[feat.accent].bg}`}>
                <feat.icon
                  className={`w-6 h-6 ${ACCENTS[feat.accent].icon}`}
                  strokeWidth={1.75}
                  aria-hidden
                />
              </div>

              <h4 className='text-sm font-semibold text-gov-dark dark:text-white leading-snug mb-1'>
                {t(feat.titleKey)}
              </h4>
              <span className='inline-block text-[11px] text-neutral-muted bg-gov-sand/60 dark:bg-emerald-100/10 dark:text-emerald-100/90 px-3 py-1 rounded-full'>
                {t(feat.subKey)}
              </span>
            </div>
          </Link>
        </motion.div>
      ))}
    </div>
  );
}
