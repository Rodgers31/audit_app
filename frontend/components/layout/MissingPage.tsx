'use client';

import Link from 'next/link';
import { useState } from 'react';
import PageShell from './PageShell';
import { COUNTY_LINKS } from '@/lib/counties/lookup';
import { normalizeCountyName } from '@/lib/counties/regions';
import { glossaryTerms } from '@/data/glossaryTerms';
import { useLang } from '@/lib/i18n/LangProvider';

const LINKS = [
  ['shell.debt', '/debt'],
  ['shell.budget_page', '/budget'],
  ['shell.counties', '/counties'],
  ['shell.audits', '/audits'],
  ['shell.learn', '/learn'],
] as const;

export default function MissingPage() {
  const { t } = useLang();
  const [query, setQuery] = useState('');
  const term = query.trim().toLowerCase();
  const countyTerm = normalizeCountyName(term);
  const counties = countyTerm ? COUNTY_LINKS.filter(county => normalizeCountyName(county.name).includes(countyTerm)).slice(0, 6) : [];
  const glossary = term ? glossaryTerms.filter(entry => entry.term.toLowerCase().includes(term)).slice(0, 6) : [];

  return (
    <PageShell title={t('shell.not_found')} subtitle={t('shell.not_found_hint')} breadcrumbs={false}>
      <div className='max-w-xl text-neutral-text'>
        <label className='block text-sm font-semibold'>
          {t('shell.search_counties_terms')}
          <input type='search' value={query} onChange={event => setQuery(event.target.value)} className='audit-control mt-2 w-full bg-surface-base' />
        </label>
        {term && (
          <ul className='mt-2 border-b border-neutral-border'>
            {counties.map(county => <li key={county.slug}><Link className='audit-receipt' href={`/counties/${county.slug}`}>{county.name}</Link></li>)}
            {glossary.map(entry => <li key={entry.id}><Link className='audit-receipt' href={`/learn/glossary#term-${encodeURIComponent(entry.id)}`}>{entry.term}</Link></li>)}
            {!counties.length && !glossary.length && <li className='py-3 text-sm'>{t('foundation.empty_list')}</li>}
          </ul>
        )}
        <ul className='mt-4 grid grid-cols-2 gap-2'>
          {LINKS.map(([name, href]) => <li key={href}><Link className='audit-control w-full justify-start' href={href}>{t(name)}</Link></li>)}
        </ul>
      </div>
    </PageShell>
  );
}
