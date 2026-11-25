'use client';

import PageShell from '@/components/layout/PageShell';
import { useLang } from '@/lib/i18n/LangProvider';
import { AUDITOR_GUIDE_MESSAGES, AUDITOR_GUIDE_STEP_COPY } from '@/lib/i18n/messages/auditorGuide';
import { ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useRef } from 'react';
import { AUDITOR_ARTICLE, AUDITOR_GUIDE_ENTRY, AUDITOR_GUIDE_STEPS, auditorGuideHref, type AuditorGuideStep } from './auditorGuideData';

const focusClass = 'rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good';
const linkClass = `audit-receipt min-w-11 justify-between ${focusClass}`;
const actionClass = `audit-control min-w-11 ${focusClass}`;

export default function AuditorGuide({ step }: { step: AuditorGuideStep }) {
  const { lang } = useLang();
  const copy = (key: keyof typeof AUDITOR_GUIDE_MESSAGES) => AUDITOR_GUIDE_MESSAGES[key][lang];
  const text = AUDITOR_GUIDE_STEP_COPY[step.key];
  const position = AUDITOR_GUIDE_STEPS.findIndex(item => item.key === step.key);
  const previous = AUDITOR_GUIDE_STEPS[position - 1];
  const next = AUDITOR_GUIDE_STEPS[position + 1];
  const heading = useRef<HTMLHeadingElement>(null);
  const previousStep = useRef(step.key);
  const value = text.value[lang]
    .replace('{figure}', String(step.figure))
    .replace('{total}', step.key === 'opinion' ? String(step.total) : '');

  useEffect(() => {
    if (previousStep.current === step.key) return;
    previousStep.current = step.key;
    heading.current?.focus();
  }, [step.key]);

  return (
    <PageShell title={copy('title')} back={{ href: AUDITOR_GUIDE_ENTRY, label: copy('back') }}>
      <div className='mx-auto min-w-0 max-w-2xl'>
        <article aria-labelledby='auditor-guide-step-heading' className='audit-panel space-y-3 p-4'>
          <p id='auditor-guide-progress' className='text-sm font-semibold text-neutral-muted'>
            {copy('progress').replace('{step}', String(position + 1)).replace('{total}', String(AUDITOR_GUIDE_STEPS.length))}
          </p>
          <h2
            ref={heading}
            id='auditor-guide-step-heading'
            tabIndex={-1}
            aria-describedby='auditor-guide-progress'
            className={`scroll-mt-28 break-words font-display text-2xl font-semibold text-neutral-text ${focusClass}`}>
            {text.title[lang]}
          </h2>
          <p className='max-w-[62ch] text-sm leading-relaxed text-neutral-text'>{text.description[lang]}</p>

          <div className='space-y-2 border-y border-neutral-border py-3'>
            {text.period && <p className='text-sm text-neutral-muted'>{text.period[lang]}</p>}
            <dl className='min-w-0'>
              <dt className='text-sm font-semibold text-neutral-text'>{text.measure[lang]}</dt>
              <dd className='audit-figure mt-1 break-words text-audit-stat text-neutral-text'>{value}</dd>
            </dl>
            <a href={step.source} className={linkClass}>
              <span className='min-w-0 break-words'>{text.source[lang]}</span>
              <ChevronRight size={16} aria-hidden='true' className='shrink-0' />
            </a>
          </div>

          <div className='flex flex-wrap items-start gap-x-5'>
            <Link href={AUDITOR_ARTICLE} className={linkClass}>
              {copy('article')} <ChevronRight size={16} aria-hidden='true' className='shrink-0' />
            </Link>
            <Link href={step.destination} className={linkClass}>
              <span className='min-w-0 break-words'>{text.destination[lang]}</span>
              <ChevronRight size={16} aria-hidden='true' className='shrink-0' />
            </Link>
          </div>
          <div className='flex flex-wrap items-center gap-2 border-t border-neutral-border pt-3'>
            {previous && <Link href={auditorGuideHref(previous)} scroll={false} className={actionClass}>{copy('previous')}</Link>}
            <Link href={next ? auditorGuideHref(next) : AUDITOR_GUIDE_ENTRY} scroll={!next} className={actionClass}>
              {copy(next ? 'next' : 'back')} <ChevronRight size={16} aria-hidden='true' className='shrink-0' />
            </Link>
          </div>
        </article>
      </div>
    </PageShell>
  );
}
