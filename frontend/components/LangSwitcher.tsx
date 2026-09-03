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
      className={`inline-flex items-center rounded-sm border border-neutral-border bg-surface-base p-0.5 dark:bg-surface-base ${
        compact ? 'text-[11px]' : 'text-[11px]'
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
            className={`min-h-7 px-2 py-1 rounded-[2px] font-mono font-semibold tracking-wide ${
              active
                ? 'bg-gov-sage text-white'
                : 'text-neutral-muted hover:bg-surface-sunken hover:text-gov-dark dark:hover:text-white'
            }`}>
            {opt.short}
          </button>
        );
      })}
    </div>
  );
}
