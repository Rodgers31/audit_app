'use client';

import PageShell from '@/components/layout/PageShell';
import { useLang } from '@/lib/i18n/LangProvider';
import { BUDGET_GUIDE_MESSAGES, BUDGET_GUIDE_STEP_COPY } from '@/lib/i18n/messages/budgetGuide';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useRef } from 'react';
import { BUDGET_GUIDE_STEPS, budgetGuideHref, readBudgetGuideFigure, type BudgetGuideStep } from './budgetGuideData';

const guidedPaths = '/learn#guided-paths';
const linkClass = 'rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good';
const actionClass = `audit-control min-w-11 ${linkClass}`;

export default function BudgetGuide({ step }: { step: BudgetGuideStep }) {
  const { lang } = useLang();
  const copy = (key: keyof typeof BUDGET_GUIDE_MESSAGES) => BUDGET_GUIDE_MESSAGES[key][lang];
  const text = BUDGET_GUIDE_STEP_COPY[step.key];
  const { data, isLoading, isError, isFetching, refetch } = useFiscalSummary();
  const heading = useRef<HTMLHeadingElement>(null);
  const previousStep = useRef(step.key);
  const position = BUDGET_GUIDE_STEPS.findIndex(item => item.key === step.key);
  const previous = BUDGET_GUIDE_STEPS[position - 1];
  const next = BUDGET_GUIDE_STEPS[position + 1];
  const figure = readBudgetGuideFigure(data, step);

  useEffect(() => {
    if (previousStep.current === step.key) return;
    previousStep.current = step.key;
    heading.current?.focus();
  }, [step.key]);

  return (
    <PageShell title={copy('title')} back={{ href: guidedPaths, label: copy('back') }}>
      <div data-budget-guide className='mx-auto min-w-0 max-w-2xl'>
        <article aria-labelledby='budget-guide-step-heading' className='audit-panel space-y-3 p-4'>
          <p id='budget-guide-progress' className='text-sm font-semibold text-neutral-muted'>
            {copy('progress').replace('{step}', String(position + 1)).replace('{total}', String(BUDGET_GUIDE_STEPS.length))}
          </p>
          <h2 id='budget-guide-step-heading' tabIndex={-1} ref={heading} aria-describedby='budget-guide-progress'
            className='break-words font-display text-2xl font-semibold text-neutral-text focus:outline-none'>
            {text.title[lang]}
          </h2>
          <p className='max-w-[62ch] text-sm leading-relaxed text-neutral-text'>{text.description[lang]}</p>

          {isLoading ? <p role='status' className='text-sm text-neutral-muted'>{copy('loading')}</p>
            : isError ? (
              <div role='alert' className='space-y-2 text-sm text-neutral-text'>
                <p>{copy('loadError')}</p>
                <button type='button' className={actionClass} disabled={isFetching} onClick={() => void refetch()}>{copy('retry')}</button>
              </div>
            ) : figure.state === 'available' ? (
              <div data-guide-figure className='space-y-2 border-y border-neutral-border py-3'>
                <p className='text-sm text-neutral-muted'>{copy('approved').replace('{year}', figure.fiscalYear)}</p>
                <dl className='min-w-0'>
                  <dt className='text-sm font-semibold text-neutral-text'>{text.measure[lang]}</dt>
                  <dd className='audit-figure mt-1 break-words text-audit-stat text-neutral-text'>
                    {copy('amount').replace('{number}', figure.amountBillion.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE',
                      { minimumFractionDigits: 1, maximumFractionDigits: 1 }))}
                  </dd>
                </dl>
                <a href={figure.sourceUrl} className={`audit-receipt min-w-11 ${linkClass}`}>
                  <span className='min-w-0 break-words'>{figure.sourceLabel}</span>
                  <ChevronRight size={16} aria-hidden='true' className='shrink-0' />
                </a>
              </div>
            ) : <p role='status' className='text-sm text-neutral-text'>{copy(figure.state).replace('{year}', figure.fiscalYear)}</p>}

          <Link href={step.destination} className={`audit-receipt min-w-11 ${linkClass}`}>
            {text.destination[lang]} <ChevronRight size={16} aria-hidden='true' className='shrink-0' />
          </Link>
          <div className='flex flex-wrap items-center gap-2 border-t border-neutral-border pt-3'>
            {previous && <Link href={budgetGuideHref(previous)} className={actionClass}>{copy('previous')}</Link>}
            <Link href={next ? budgetGuideHref(next) : guidedPaths} className={actionClass}>
              {copy(next ? 'next' : 'back')} <ChevronRight size={16} aria-hidden='true' className='shrink-0' />
            </Link>
          </div>
        </article>
      </div>
    </PageShell>
  );
}
