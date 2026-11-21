'use client';

import Link from 'next/link';
import PublicSearch from '@/components/search/PublicSearch';
import PageShell from './PageShell';
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
  return (
    <PageShell title={t('shell.not_found')} subtitle={t('shell.not_found_hint')} breadcrumbs={false} titleStyle='inline'>
      <div className='max-w-xl text-neutral-text'>
        <PublicSearch compact />
        <ul className='mt-4 divide-y divide-neutral-border border-b border-neutral-border'>
          {LINKS.map(([name, href]) => (
            <li key={href}>
              <Link className='flex min-h-11 items-center text-sm font-semibold underline-offset-4 hover:underline' href={href}>{t(name)}</Link>
            </li>
          ))}
        </ul>
      </div>
    </PageShell>
  );
}
