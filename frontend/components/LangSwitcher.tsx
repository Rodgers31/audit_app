/**
 * Compact language switcher — 3-way radio rendered as a pill group.
 * Sits in the header next to the auth button. Small enough not to
 * crowd the nav but visible enough to invite exploration.
 */
'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import type { Lang } from '@/lib/i18n/messages';

const OPTIONS: Array<{ value: Lang; short: string; title: string }> = [
  { value: 'en', short: 'EN', title: 'English' },
  { value: 'sw', short: 'SW', title: 'Kiswahili' },
  { value: 'plain', short: 'Aa', title: 'Plain English' },
];

export default function LangSwitcher({ compact = false }: { compact?: boolean }) {
  const { lang, setLang, t } = useLang();

  return (
    <div
      role='radiogroup'
      aria-label={t('lang.label')}
      className={`inline-flex items-center rounded-full bg-white/[0.07] ring-1 ring-inset ring-white/15 p-0.5 ${
        compact ? 'text-[10px]' : 'text-[11px]'
      }`}>
      {OPTIONS.map((opt) => {
        const active = lang === opt.value;
        return (
          <button
            key={opt.value}
            type='button'
            role='radio'
            aria-checked={active}
            title={opt.title}
            onClick={() => setLang(opt.value)}
            className={`px-2 py-1 rounded-full font-semibold tracking-wide transition-colors ${
              active
                ? 'bg-gov-sage text-gov-dark dark:text-white shadow-sm'
                : 'text-white/70 hover:text-white hover:bg-white/5'
            }`}>
            {opt.short}
          </button>
        );
      })}
    </div>
  );
}
