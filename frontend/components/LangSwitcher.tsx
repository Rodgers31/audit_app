'use client';

import { useId } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';
import type { Lang } from '@/lib/i18n/messages';

const OPTIONS: Array<{ value: Lang; text: string; language?: string }> = [
  { value: 'en', text: 'English', language: 'en' },
  { value: 'sw', text: 'Kiswahili', language: 'sw' },
  { value: 'plain', text: 'Plain English', language: 'en' },
];

export default function LangSwitcher() {
  const { lang, setLang, t } = useLang();
  const name = useId();
  return (
    <div className='min-w-0'>
      <p id={`${name}-label`} className='mb-2 text-sm font-semibold'>{t('lang.label')}</p>
      <div role='radiogroup' aria-labelledby={`${name}-label`} className='flex flex-wrap gap-1'>
        {OPTIONS.map(({ value, text, language }) => (
          <label key={value} className='relative inline-flex min-h-11 items-center'>
            <input type='radio' name={name} className='peer absolute inset-0 h-full w-full cursor-pointer opacity-0' value={value} checked={lang === value} onChange={() => setLang(value)} />
            <span lang={language} className='audit-control cursor-pointer px-2 peer-checked:border-gov-sage peer-checked:bg-gov-sage peer-checked:text-white peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2'>
              {text}
            </span>
          </label>
        ))}
      </div>
      <p className='mt-2 text-xs text-neutral-muted'>{t('shell.language_explained')}</p>
    </div>
  );
}
