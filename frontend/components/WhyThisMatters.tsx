'use client';

import { evidenceUrl } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import { fmtKES } from '@/lib/utils';
import { ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { whyMoneyMatters as copy } from './why-this-matters/messages';

const services = ['health', 'education', 'roads'] as const;
type Service = typeof services[number];

/** An admitted pair from the same county reporting period and population. See #1017. */
export type CountyServiceObservation = {
  basis: 'published-county-implementation';
  allocatedKes: number;
  spentKes: number;
  period: string;
  countyCount: number;
  source: { publisher: string; url: string };
};

const actions = [
  { title: 'readAudit', label: 'choose', href: '/counties' },
  { title: 'budgetMeeting', label: 'article', href: '/learn?article=201#constitution-book' },
  { title: 'askMca', label: 'findings', href: '/audits' },
  { title: 'correct', label: 'email', href: 'mailto:auditgava@gmail.com' },
] as const;

function sourceLink(observation?: CountyServiceObservation) {
  if (!observation || observation.basis !== 'published-county-implementation' ||
      !Number.isFinite(observation.allocatedKes) || observation.allocatedKes <= 0 ||
      !Number.isFinite(observation.spentKes) || observation.spentKes < 0 ||
      !Number.isFinite(observation.spentKes / observation.allocatedKes * 100) ||
      !observation.period.trim() || !observation.source.publisher.trim() ||
      !Number.isInteger(observation.countyCount) || observation.countyCount < 1 || observation.countyCount > 47) return null;
  return evidenceUrl(observation.source.url);
}

export default function WhyThisMatters({ observations = {} }: {
  observations?: Partial<Record<Service, CountyServiceObservation>>;
}) {
  const { lang } = useLang();
  const percent = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { style: 'percent', maximumFractionDigits: 1 });

  return (
    <div className='min-w-0 space-y-6 text-neutral-text'>
      <div className='grid min-w-0 grid-cols-1 gap-4 md:grid-cols-3 md:gap-6'>
        {services.map(service => {
          const report = observations[service];
          const href = sourceLink(report);
          return (
            <section key={service} aria-labelledby={`why-${service}`} className='min-w-0 space-y-2 border-b border-neutral-border pb-3 md:border-t md:py-3'>
              <h2 id={`why-${service}`} className='font-display text-audit-heading font-semibold'>{copy[service][lang]}</h2>
              {report && href ? (
                <>
                  <dl className='divide-y divide-neutral-border text-sm'>
                    <div className='flex flex-wrap items-baseline justify-between gap-x-2 border-t border-neutral-border py-2'>
                      <dt>{copy.budgeted[lang]}</dt><dd className='font-semibold tabular-nums'>{fmtKES(report.allocatedKes)}</dd>
                    </div>
                    <div className='flex flex-wrap items-baseline justify-between gap-x-2 py-2'>
                      <dt>{copy.spent[lang]}</dt><dd className='font-semibold tabular-nums'>{percent.format(report.spentKes / report.allocatedKes)}</dd>
                    </div>
                  </dl>
                  <p className='text-sm text-neutral-muted'>{copy.coverage[lang].replace('{count}', String(report.countyCount))}</p>
                  <a href={href} className='audit-receipt max-w-full break-words'>
                    {report.source.publisher} · {report.period}
                  </a>
                </>
              ) : <p className='text-sm leading-relaxed text-neutral-muted'>{copy.unavailable[lang]}</p>}
            </section>
          );
        })}
      </div>
      <Link href='/transparency#county-spending-heading' className='audit-control inline-flex'>{copy.spending[lang]}</Link>
      <section aria-labelledby='why-action-title' className='min-w-0'>
        <h2 id='why-action-title' className='font-display text-audit-heading font-semibold'>{copy.actions[lang]}</h2>
        <ul className='mt-2 divide-y divide-neutral-border border-y border-neutral-border'>
          {actions.map(({ title, label, href }) => (
            <li key={title}>
              <Link href={href} className='flex min-h-11 flex-col items-start gap-1 rounded py-2 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-good'>
                <span>{copy[title][lang]}</span>
                <span className='flex items-center gap-1 text-signal-good underline underline-offset-4'>{copy[label][lang]}<ChevronRight size={16} aria-hidden='true' /></span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
