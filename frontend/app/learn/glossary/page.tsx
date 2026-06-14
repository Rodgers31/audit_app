/**
 * /learn/glossary — Plain-English index of government finance terms.
 */
'use client';

import InteractiveGlossary from '@/components/InteractiveGlossary';
import PageShell from '@/components/layout/PageShell';
import { glossaryTerms, GLOSSARY_CATEGORIES } from '@/data/glossaryTerms';

export default function GlossaryPage() {
  const termCount = glossaryTerms.length;
  const themeCount = GLOSSARY_CATEGORIES.length - 1;

  return (
    <PageShell
      title='Plain-English glossary'
      subtitle='Every budget, audit and finance term on this site, translated into language that actually makes sense — with real examples and links to the Constitution.'
      back={{ href: '/learn', label: 'Back to Learning Hub' }}>
      <div className='flex flex-wrap items-center justify-end gap-4 text-[12.5px] text-neutral-muted'>
        <span>
          <strong className='text-gov-dark dark:text-white'>{termCount}</strong> terms
        </span>
        <span className='text-neutral-border'>·</span>
        <span>
          <strong className='text-gov-dark dark:text-white'>{themeCount}</strong> themes
        </span>
        <span className='text-neutral-border'>·</span>
        <span>Linked to the Constitution</span>
      </div>

      <InteractiveGlossary />
    </PageShell>
  );
}
