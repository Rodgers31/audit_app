'use client';

import { useDataFreshness } from '@/components/DataFreshnessBadge';
import PageShell from '@/components/layout/PageShell';
import { useLang } from '@/lib/i18n/LangProvider';
import { SOURCES_MESSAGES } from '@/lib/i18n/messages/sources';
import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import { ABOUT_MESSAGES } from './messages';

const PRACTICES = [
  { title: 'figures', detail: 'figuresDetail' },
  { title: 'findings', detail: 'findingsDetail' },
  { title: 'modelled', detail: 'modelledDetail' },
] as const;

const PUBLISHERS = [
  { code: 'CBK', name: 'cbk', reports: 'cbkReports' },
  { code: 'Treasury', name: 'treasury', reports: 'treasuryReports' },
  { code: 'OAG', name: 'oag', reports: 'oagReports' },
  { code: 'COB', name: 'cob', reports: 'cobReports' },
] as const;

const CONTACT_EMAIL = 'auditgava@gmail.com';

const HEADING = 'font-display text-audit-heading font-semibold text-neutral-text';
const LINK = 'inline-flex min-h-11 min-w-11 max-w-full items-center text-sm font-medium text-signal-good underline underline-offset-4 [overflow-wrap:anywhere] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal-good';

export default function AboutPage() {
  const { lang } = useLang();
  const { data, isError } = useDataFreshness();
  const copy = (key: keyof typeof ABOUT_MESSAGES) => ABOUT_MESSAGES[key][lang];
  const sources = !isError && Array.isArray(data?.sources) ? data.sources : [];

  return (
    <PageShell title={copy('title')} subtitle={copy('intro')} breadcrumbs={false}>
      <div className='grid min-w-0 gap-y-6 min-[900px]:grid-cols-2 min-[900px]:gap-x-12'>
        <section className='min-w-0' aria-labelledby='about-practices'>
          <h2 id='about-practices' className={HEADING}>{copy('practices')}</h2>
          <ul className='mt-2 divide-y divide-neutral-border border-b border-neutral-border'>
            {PRACTICES.map(({ title, detail }) => (
              <li key={title} className='py-3'>
                <h3 className='text-base font-semibold text-neutral-text'>{copy(title)}</h3>
                <p className='mt-1 max-w-[70ch] text-sm leading-relaxed text-neutral-muted'>{copy(detail)}</p>
              </li>
            ))}
          </ul>
          <p className='mt-4 max-w-[70ch] text-sm leading-relaxed text-neutral-muted'>{copy('name')}</p>
        </section>

        <div className='min-w-0 space-y-5'>
          <section aria-labelledby='about-sources'>
            <h2 id='about-sources' className={HEADING}>{copy('sources')}</h2>
            <dl className='mt-2 divide-y divide-neutral-border border-b border-neutral-border'>
              {PUBLISHERS.map(({ code, name, reports }) => {
                const matches = sources.filter((entry) => entry?.source === code);
                const [source] = matches;
                const period = matches.length === 1 && source && 'covers_through' in source &&
                  typeof source.covers_through === 'string' ? source.covers_through.trim() : '';

                return (
                  <div key={code} className='py-2'>
                    <dt className='text-sm font-semibold text-neutral-text'>{copy(name)}</dt>
                    <dd className='text-sm leading-relaxed text-neutral-muted'>{copy(reports)}</dd>
                    {period && (
                      <dd className='text-sm leading-relaxed text-neutral-muted [overflow-wrap:anywhere]'>
                        {SOURCES_MESSAGES.acceptedCoverage[lang].replace('{period}', () => period)}
                      </dd>
                    )}
                  </div>
                );
              })}
            </dl>
            <Link href='/sources' className='audit-receipt text-signal-good'>
              {copy('viewSources')}
              <ArrowRight size={16} aria-hidden='true' />
            </Link>
          </section>

          <section aria-labelledby='about-contact'>
            <h2 id='about-contact' className={HEADING}>{copy('contact')}</h2>
            <p className='mt-2 max-w-[70ch] text-sm leading-relaxed text-neutral-muted'>{copy('contactDetail')}</p>
            <a href={`mailto:${CONTACT_EMAIL}`} className={LINK}>{CONTACT_EMAIL}</a>
          </section>

          <nav aria-label={copy('policies')}>
            <ul className='flex flex-wrap gap-x-5'>
              <li><Link href='/privacy' className={LINK}>{copy('privacy')}</Link></li>
              <li><Link href='/terms' className={LINK}>{copy('terms')}</Link></li>
            </ul>
          </nav>
        </div>
      </div>
    </PageShell>
  );
}
